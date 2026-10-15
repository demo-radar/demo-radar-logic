"""Offline adapter for container checks without a model or network call."""

import json

from service.providers.base import ProviderResult


class SyntheticProvider:
    """Offline fixture for Docker/API checks; not a classifier or fallback.

    A synthetic title containing 'rad' returns mobility; others abstain. Returned
    metadata explicitly identifies this as synthetic and supplies no usage.
    It never calls Qwen, Gemini, or any network endpoint.
    """

    async def predict(self, payload: dict) -> ProviderResult:
        """Return an invented answer from the configured title payload."""
        title = json.loads(payload["messages"][-1]["content"])["title"]
        tags = ["mobility"] if "rad" in title.lower() else []
        return ProviderResult(
            tags, {"model": "synthetic-fixture-not-qwen", "usage": None, "id": None}
        )
