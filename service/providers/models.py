"""Approved runtime models and their reviewed pricing, grouped by provider metadata."""

from dataclasses import dataclass
from enum import StrEnum


class ModelId(StrEnum):
    QWEN = "Qwen/Qwen3.6-35B-A3B-FP8"
    GEMINI_FLASH = "gemini-3.8-flash"


@dataclass(frozen=True)
class ModelDefinition:
    """Provider ownership and optional paid pricing for one approved model."""

    provider: str
    pricing: dict | None = None
    requires_free_account: bool = False


MODEL_CATALOG = {
    # Hetzner execution still requires the operator's free-account confirmation.
    ModelId.QWEN: ModelDefinition(provider="hetzner", requires_free_account=True),
    ModelId.GEMINI_FLASH: ModelDefinition(
        provider="gemini",
        pricing={
            "version": "gemini-3.8-flash-standard-2026-10-18",
            "currency": "USD",
            "model": ModelId.GEMINI_FLASH,
            "valid_from": "2026-10-18",
            "valid_until": "2026-12-31",
            "input_microusd_per_token": "0.75",
            "output_microusd_per_token": "3.75",
            "maximum_input_tokens": 1048576,
            "maximum_output_tokens": 65536,
        },
    ),
}
