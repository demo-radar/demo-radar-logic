"""Hetzner transport using the current URL while retaining saved profile identities."""

from service.providers.chat_completions import (
    ChatCompletionsProvider,
    parse_response,  # noqa: F401
    retry_delay,  # noqa: F401
    strict_json,  # noqa: F401
)


class HetznerProvider(ChatCompletionsProvider):
    PROVIDER = "hetzner"
    ENDPOINT = "https://inference.hetzner.com/v1/chat/completions"
    LEGACY_ENDPOINT = "https://inference.hetzner.com/api/v1/chat/completions"
    CONFIG_ENDPOINTS = (ENDPOINT, LEGACY_ENDPOINT)
