"""Synthetic runtime settings preserve dispatch guards and saved-job identities."""

import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from service.config import Settings


def runtime(**values):
    with patch.dict(
        os.environ, {"DEMOLOGIC_SERVICE_TOKEN": "synthetic-token", **values}, clear=True
    ):
        return Settings.from_env()


@pytest.mark.parametrize(
    "name,field",
    [
        ("DEMOLOGIC_FREE_TIER_CONFIRMED", "free_tier_confirmed"),
        ("DEMOLOGIC_SUMMARY_ENABLED", "summary_enabled"),
        ("DEMOLOGIC_GEMINI_ENABLED", "gemini_enabled"),
    ],
)
def test_activation_flags_share_strict_case_insensitive_parsing(name, field):
    assert getattr(runtime(**{name: " TRUE "}), field) is True
    assert getattr(runtime(**{name: "False"}), field) is False
    for value in ("", "1", "yes", "private-invalid-value"):
        with pytest.raises(ValueError) as caught:
            runtime(**{name: value})
        if value:
            assert value not in str(caught.value)


@pytest.mark.parametrize(
    "name,value",
    [
        ("DEMOLOGIC_TIMEOUT_SECONDS", "61"),
        ("DEMOLOGIC_MIN_INTERVAL_SECONDS", "nan"),
        ("DEMOLOGIC_MIN_INTERVAL_SECONDS", "inf"),
        ("DEMOLOGIC_MAX_ATTEMPTS_PER_EVENT", "0"),
        ("DEMOLOGIC_SUMMARY_MAX_ATTEMPTS", "4"),
        ("DEMOLOGIC_SUMMARY_TIMEOUT_SECONDS", "0"),
    ],
)
def test_numeric_environment_bounds(name, value):
    with pytest.raises(ValueError):
        runtime(**{name: value})


def test_missing_defaults_overrides_secrets_and_dataclass_compatibility():
    original = runtime()
    assert original.mode == "demo"
    assert not original.gemini_enabled
    assert not original.summary_enabled
    assert original.max_attempts_per_event == 3
    assert original.summary_max_attempts == 3
    assert original.paid_run_usd == ""
    assert replace(original, max_attempts_per_event=1).max_attempts_per_event == 1
    configured = runtime(
        HETZNER_API_KEY="private-key",
        GEMINI_API_KEY="another-private-key",
        DEMOLOGIC_MAX_ATTEMPTS_PER_EVENT="1",
    )
    assert configured.max_attempts_per_event == 1
    for secret in ("private-key", "another-private-key", "synthetic-token"):
        assert secret not in repr(configured)
    with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError):
        Settings.from_env()
    with pytest.raises(ValueError):
        runtime(DEMOLOGIC_MODE="live")
    with pytest.raises(ValueError) as caught:
        runtime(DEMOLOGIC_TIMEOUT_SECONDS="private-invalid-value")
    assert "private-invalid-value" not in str(caught.value)


def test_examples_and_compose_forward_the_supported_runtime_variables():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "compose.yml").read_text()
    example = (root / "service/.env.example").read_text()
    # Compose fixes the journal to its persistent mount rather than accepting a host path.
    import re

    names = set(
        re.findall(
            r'(?:env_bool|env_number|os.environ.get)\("([A-Z_]+)"',
            (root / "service/config.py").read_text(),
        )
    )
    for name in names:
        assert name + ":" in compose
        if name != "DEMOLOGIC_DATABASE":
            assert name + "=" in example


def test_pydantic_settings_preserve_dataclass_callers_and_hide_failed_inputs():
    from dataclasses import FrozenInstanceError, asdict

    settings = runtime()
    updated = replace(settings, timeout_seconds=1)
    assert type(updated.timeout_seconds) is int
    assert asdict(updated)["timeout_seconds"] == 1
    assert updated.config_id == settings.config_id
    assert updated.database == settings.database
    assert updated.paid_run_usd == settings.paid_run_usd
    with pytest.raises(FrozenInstanceError):
        updated.gemini_enabled = True
    for changes in (
        {"gemini_enabled": "false"},
        {"min_interval_seconds": float("nan")},
        {"timeout_seconds": 61},
    ):
        with pytest.raises(ValueError) as caught:
            replace(settings, provider_key="synthetic-private-key", **changes)
        assert "synthetic-private-key" not in str(caught.value)
        assert "synthetic-token" not in str(caught.value)
    with pytest.raises(ValueError):
        replace(settings, unknown_option=True)
