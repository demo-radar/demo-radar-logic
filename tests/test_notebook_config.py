"""Local notebook configuration stays explicit, safe by default and separate from secrets."""

import json

import pytest

from notebooks.tools.config import load_notebook_env


def test_missing_env_uses_cache_only_defaults(tmp_path):
    settings, keys = load_notebook_env(tmp_path, environ={})
    assert settings == {
        "run_live": False,
        "stage": "check",
        "providers": ["groq", "hetzner"],
        "max_retry_wait_seconds": 120,
    }
    assert not any(keys.values())


def test_keys_are_separate_and_env_is_reread_without_mutation(tmp_path):
    path = tmp_path / ".env"
    path.write_text('GROQ_API_KEY="fake-private-key"\nNOTEBOOK07_RUN_LIVE=false\n')
    process_env = {}
    settings, keys = load_notebook_env(tmp_path, environ=process_env)
    assert not settings["run_live"] and keys["GROQ_API_KEY"] == "fake-private-key"
    assert "fake-private-key" not in json.dumps(settings)
    assert process_env == {}
    path.write_text("NOTEBOOK07_RUN_LIVE=true\nNOTEBOOK07_STAGE=screen\n")
    settings, keys = load_notebook_env(tmp_path, environ=process_env)
    assert settings["run_live"] and settings["stage"] == "screen"
    assert keys["GROQ_API_KEY"] == ""


def test_process_variables_override_file_and_no_interpolation(tmp_path):
    (tmp_path / ".env").write_text('GROQ_API_KEY="${OTHER_SECRET}"\nNOTEBOOK07_STAGE=screen\n')
    settings, keys = load_notebook_env(tmp_path, environ={"NOTEBOOK07_STAGE": "check"})
    assert settings["stage"] == "check" and keys["GROQ_API_KEY"] == "${OTHER_SECRET}"


@pytest.mark.parametrize(
    "name,value",
    [
        ("RUN_LIVE", "maybe"),
        ("STAGE", "final"),
        ("PROVIDERS", "groq,groq"),
        ("PROVIDERS", "unknown"),
        ("MAX_RETRY_WAIT_SECONDS", "nan"),
        ("MAX_RETRY_WAIT_SECONDS", "241"),
        ("MAX_RETRY_WAIT_SECONDS", "-1"),
    ],
)
def test_invalid_controls_fail_before_inference(tmp_path, name, value):
    with pytest.raises(ValueError, match="NOTEBOOK07_"):
        load_notebook_env(tmp_path, environ={f"NOTEBOOK07_{name}": value})
