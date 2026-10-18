"""Shared provider interface, return value and sanitized failure contract."""

from dataclasses import dataclass
from typing import Protocol


class ProviderFailure(Exception):
    """Provider error with a sanitized message and conservative outcome state."""

    def __init__(self, code, status=502, unknown=False, metadata=None, retry_after=0):
        self.code = code
        self.status = status
        self.unknown = unknown
        self.metadata = metadata or {}
        self.retry_after = retry_after


@dataclass(frozen=True)
class ProviderResult:
    """Vendor-neutral return value: approved tags plus model/request/usage metadata.

    ``tags=[]`` is an abstention. Invalid output raises ProviderFailure instead;
    it must never be silently converted to an empty successful prediction.
    """

    tags: list[str]
    metadata: dict


class TagProvider(Protocol):
    """Interface used by InferenceService instead of concrete vendor clients.

    Implementations receive the selected configuration's payload and return a
    ProviderResult. They must make at most one request, normalize usage without
    inventing missing counts, and raise ProviderFailure for invalid output.
    """

    async def predict(self, payload: dict) -> ProviderResult:
        """Submit one independent request; never retry or switch models internally."""
        ...


def response_metadata(body):
    """Keep valid identity/usage fields even if the generated tags are invalid.

    Do not retain the completion text or other response fields. Invalid metadata
    fields become null in a failed result; they are never misreported as usage.
    """
    body = body if isinstance(body, dict) else {}
    return {
        "model": body.get("model") if isinstance(body.get("model"), str) else None,
        "id": body.get("id") if isinstance(body.get("id"), str) else None,
        "usage": body.get("usage") if isinstance(body.get("usage"), dict) else None,
    }
