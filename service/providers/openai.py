"""OpenAI uses the shared completion transport and paid-call safeguards."""

import json

from service.providers.chat_completions import ChatCompletionsProvider


class OpenAIProvider(ChatCompletionsProvider):
    PROVIDER = "openai"
    ENDPOINT = "https://api.openai.com/v1/chat/completions"
    CONFIG_ENDPOINTS = (ENDPOINT,)

    @staticmethod
    def payload(payload):
        # Only reviewed model settings are sent. Disable storage and vendor extensions.
        return {
            key: value
            for key, value in payload.items()
            if key
            in {"model", "messages", "max_completion_tokens", "response_format", "reasoning_effort"}
        } | {"store": False, "service_tier": "default"}

    async def count_tokens(self, payload):
        """Reserve a conservative UTF-8 byte bound, plus the shared protocol margin."""
        # For the fixed text-only messages, bytes bound byte-pair input tokens.
        # Include the entire serialized schema and settings. This is a reservation
        # bound, not measured provider usage; returned usage settles the charge.
        return len(json.dumps(self.payload(payload), ensure_ascii=False).encode("utf-8"))

    async def response_body(self, payload):
        return await super().response_body(self.payload(payload))
