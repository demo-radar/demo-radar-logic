"""Native Gemini transport with bounded JSON output and no retries or tools."""

import json

import httpx

from service.providers.base import ProviderFailure, ProviderResult, response_metadata
from service.providers.hetzner import parse_response, retry_delay, strict_json
from service.providers.models import MODEL_CATALOG


class GeminiProvider:
    """Use only the reviewed model endpoint; credentials stay in the service."""

    @staticmethod
    def endpoint_for(model):
        """Allow only registered Gemini models on Google's fixed API host."""
        definition = MODEL_CATALOG.get(model)
        if definition is None or definition.provider != "gemini":
            return None
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, client, config, key):
        endpoint = self.endpoint_for(config.model)
        if config.provider != "gemini" or endpoint is None or config.endpoint != endpoint:
            raise ValueError("Unsupported Gemini model or endpoint")
        self.client, self.key, self.config = client, key, config
        self.model, self.endpoint = config.model, endpoint

    def payload(self, payload):
        """Translate the pinned messages and schema; never forward arbitrary options."""
        schema = payload.get("response_format", {}).get("json_schema", {}).get("schema")
        if schema is None:
            from demo_logic.taxonomy import topic_tags

            schema = {
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "maxItems": 2,
                        "items": {"type": "string", "enum": sorted(topic_tags("v2"))},
                    }
                },
                "required": ["tags"],
                "additionalProperties": False,
            }
        return {
            "systemInstruction": {
                "parts": [
                    {"text": message["content"]}
                    for message in payload["messages"]
                    if message["role"] == "system"
                ]
            },
            "contents": [
                {
                    "role": "model" if message["role"] == "assistant" else "user",
                    "parts": [{"text": message["content"]}],
                }
                for message in payload["messages"]
                if message["role"] != "system"
            ],
            "generationConfig": {
                "temperature": payload["temperature"],
                "candidateCount": 1,
                "maxOutputTokens": payload["max_completion_tokens"],
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }

    async def count_tokens(self, payload):
        """Count the complete native request without generating an answer."""
        native = self.payload(payload)
        # countTokens omits output schemas; count their serialized config as text too.
        native["contents"][-1]["parts"].append(
            {"text": json.dumps(native["generationConfig"], ensure_ascii=False)}
        )
        body = {"generateContentRequest": {"model": f"models/{self.model}", **native}}
        try:
            async with self.client.stream(
                "POST",
                self.endpoint.replace(":generateContent", ":countTokens"),
                json=body,
                headers={"x-goog-api-key": self.key},
            ) as response:
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 8192:
                        raise ValueError("Token count response too large")
            if response.status_code != 200:
                raise ValueError("Token count unavailable")
            count = strict_json(chunks)["totalTokens"]
            pricing = MODEL_CATALOG[self.model].pricing
            if (
                pricing is None
                or type(count) is not int
                or not 0 <= count <= pricing["maximum_input_tokens"]
            ):
                raise ValueError("Invalid token count")
            return count
        except (httpx.RequestError, ValueError, TypeError, KeyError) as exc:
            raise ProviderFailure("token_count_unavailable", status=503) from exc

    async def response_body(self, payload):
        """Make exactly one call and retain usage even when the answer is invalid."""
        async with self.client.stream(
            "POST", self.endpoint, json=self.payload(payload), headers={"x-goog-api-key": self.key}
        ) as response:
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > 262144:
                    raise ProviderFailure("provider_response_too_large", unknown=True)
        if response.status_code != 200:
            raise ProviderFailure(
                f"provider_http_{response.status_code}",
                # Quota stays 429; invalid credentials pause work with 503.
                # Other upstream failures use our gateway-error response.
                status={429: 429, 401: 503, 403: 503}.get(response.status_code, 502),
                unknown=response.status_code >= 500,
                retry_after=retry_delay(response.headers.get("Retry-After", "0")),
            )
        try:
            body = strict_json(chunks)
        except (ValueError, TypeError) as exc:
            raise ProviderFailure("invalid_provider_json", unknown=True) from exc
        if not isinstance(body, dict):
            raise ProviderFailure("invalid_provider_response", unknown=True)
        usage = body.get("usageMetadata")
        normalized = None
        if isinstance(usage, dict):

            def count(key):
                value = usage.get(key)
                return value if type(value) is int and value >= 0 else None

            output, thinking = count("candidatesTokenCount"), count("thoughtsTokenCount")
            # A missing count remains unknown; it is never evidence of zero spend.
            normalized = {
                "prompt_tokens": count("promptTokenCount"),
                "completion_tokens": output + thinking
                if output is not None and thinking is not None
                else None,
                "total_tokens": count("totalTokenCount"),
                "prompt_tokens_details": {"cached_tokens": count("cachedContentTokenCount")},
                "completion_tokens_details": {"reasoning_tokens": thinking},
                "gemini": usage,
            }
        result = {
            "model": body.get("modelVersion"),
            "id": body.get("responseId"),
            "usage": normalized,
        }
        metadata = response_metadata(result)
        try:
            candidates = body["candidates"]
            if (
                len(candidates) != 1
                or candidates[0]["finishReason"] != "STOP"
                or result["model"] != self.model
            ):
                raise ValueError("Incomplete or mismatched response")
            parts = candidates[0]["content"]["parts"]
            content = "".join(part["text"] for part in parts if part.get("thought") is not True)
            result["choices"] = [{"finish_reason": "stop", "message": {"content": content}}]
            return result
        except (TypeError, KeyError, IndexError, ValueError, AttributeError) as exc:
            raise ProviderFailure("invalid_provider_response", metadata=metadata) from exc

    async def predict(self, payload):
        body = await self.response_body(payload)
        return ProviderResult(parse_response(body), response_metadata(body))

