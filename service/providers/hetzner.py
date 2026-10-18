"""Hetzner Qwen adapter: one HTTP call, bounded response and tag validation.

The model and prompt come from the evaluated configuration. This module owns
Hetzner's URL, HTTP error interpretation and response format. Helpers stay pure;
the QwenProvider object owns the client and credential for the application life.
"""

import json
import math
import time
from email.utils import parsedate_to_datetime

from service.inference.validation import validate_tags
from service.providers.base import ProviderFailure, ProviderResult, response_metadata


def strict_json(value):
    """Decode unambiguous, finite JSON that can safely be saved and returned.

    Python normally accepts duplicate keys and NaN. Reject those, deeply nested
    responses, and invalid Unicode instead of committing an unrenderable result.
    """

    def unique_object(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = item
        return result

    try:
        result = json.loads(value, object_pairs_hook=unique_object)
        json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Unsupported JSON encoding or nesting") from exc
    return result


def retry_delay(header):
    """Read seconds or an HTTP-date; preserve long provider cooldowns.

    A malformed or non-finite value supplies no usable delay. Fractional seconds
    are retained internally and rounded up when sent in an HTTP response header.
    """
    try:
        delay = float(header)
    except ValueError:
        try:
            delay = parsedate_to_datetime(header).timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            return 0
    return max(0, delay) if math.isfinite(delay) else 0


def parse_response(body):
    """Validate complete JSON, model identity and zero to two approved tags.

    Empty tags are a valid abstention. Unknown, duplicate or excessive tags,
    truncated completions and added fields are failures, not empty successes.
    Keep this contract equal to the evaluated notebook parser.
    """
    try:
        choice = body["choices"][0]
        if (
            choice["finish_reason"] != "stop"
            or not isinstance(body["model"], str)
            or not body["model"]
            or (body.get("id") is not None and not isinstance(body["id"], str))
            or (body.get("usage") is not None and not isinstance(body["usage"], dict))
        ):
            raise ValueError("Incomplete completion")
        parsed = strict_json(choice["message"]["content"])
        tags = parsed["tags"]
        if set(parsed) != {"tags"}:
            raise ValueError("Invalid tags")
        validate_tags(tags, response_metadata(body))
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ProviderFailure(
            "invalid_provider_response", metadata=response_metadata(body)
        ) from exc
    return tags


class QwenProvider:
    """Hetzner adapter for the evaluated Qwen configuration.

    Args:
        client: Lifecycle-owned HTTPX client; this adapter does not close it.
        config: Approved endpoint/model configuration.
        key: Private provider credential, used only in the authorization header.
    """

    ENDPOINT = "https://inference.hetzner.com/api/v1/chat/completions"

    def __init__(self, client, config, key):
        """Check the approved destination before retaining a private credential.

        Raises:
            ValueError: The configuration does not belong to this adapter.
        The endpoint is owned by this class; callers cannot redirect a request.
        """
        if config.provider != "hetzner" or config.endpoint != self.ENDPOINT:
            raise ValueError("QwenProvider requires the approved Hetzner endpoint")
        self.client, self.key = client, key

    async def predict(self, payload: dict) -> ProviderResult:
        """Return validated tags and usage from exactly one bounded Qwen call."""
        tags, body = await self._request(payload)
        return ProviderResult(tags, response_metadata(body))

    async def _request(self, payload: dict):
        """Send exactly one attempt, with no automatic retry, repair or fallback.

        HTTPX timeouts bound I/O inactivity; the API adds a total elapsed deadline.
        Redirects are disabled, preventing credential forwarding to another endpoint.
        Provider error bodies and credentials are never returned in the API response.
        """
        body = await self.response_body(payload)
        return parse_response(body), body

    async def response_body(self, payload: dict):
        """Read one bounded completion envelope for tag or summary adapters.

        Output parsing belongs to the task adapter. All tasks share this URL,
        credential handling, error mapping and size bound. No automatic retry.
        """
        async with self.client.stream(
            "POST", self.ENDPOINT, json=payload, headers={"Authorization": f"Bearer {self.key}"}
        ) as response:
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > 262144:
                    raise ProviderFailure("provider_response_too_large", unknown=True)
        if response.status_code != 200:
            # Read only the already-bounded body. Extract known fields, never the
            # provider's free-text error message, which may echo private input.
            try:
                error_body = strict_json(chunks)
            except ValueError:
                error_body = {}
            error = error_body.get("error") if isinstance(error_body, dict) else None
            error = error if isinstance(error, dict) else {}
            hard_quota = {
                "insufficient_quota",
                "credit_balance_exhausted",
                "billing_hard_limit_reached",
            }
            exhausted = any(
                isinstance(error.get(key), str) and error[key] in hard_quota
                for key in ("code", "type")
            )
            code = (
                "provider_quota_exhausted" if exhausted else f"provider_http_{response.status_code}"
            )
            status = (
                429
                if response.status_code == 429
                else 503
                if response.status_code in {401, 403}
                else 502
            )
            raise ProviderFailure(
                code,
                status,
                unknown=response.status_code >= 500,
                metadata=response_metadata(error_body),
                retry_after=retry_delay(response.headers.get("Retry-After", "0")),
            )
        try:
            body = strict_json(chunks)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderFailure("invalid_provider_json", unknown=True) from exc
        return body
