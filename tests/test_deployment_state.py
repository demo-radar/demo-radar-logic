"""Deployment control must retain the journal and refuse active or uncertain work."""

import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

spec = importlib.util.spec_from_file_location(
    "deployment_state", Path(__file__).resolve().parents[1] / "scripts/deploy/state.py"
)
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


def test_journal_must_exist_at_the_persistent_mount(monkeypatch):
    monkeypatch.setenv("DEMOLOGIC_DATABASE", "/tmp/new-empty.sqlite")
    with pytest.raises(RuntimeError, match="existing inference journal"):
        state.check_journal()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(state, "check_journal", lambda: None)
    monkeypatch.setenv("DEMOLOGIC_SERVICE_TOKEN", "synthetic-private-token")
    return monkeypatch


def test_pause_uses_existing_internal_token_and_never_infers(client):
    def response(request, timeout):
        assert request.full_url == "http://localhost:8000/v1/maintenance"
        assert request.method == "POST"
        assert request.get_header("Authorization") == "Bearer synthetic-private-token"
        assert timeout == 15
        return io.BytesIO(
            json.dumps({"maintenance": True, "drained": True, "unresolved_attempts": 0}).encode()
        )

    client.setattr(state, "urlopen", response)
    state.control("pause")


@pytest.mark.parametrize(
    "payload",
    [
        {"maintenance": True, "drained": False, "unresolved_attempts": 1},
        {"maintenance": False, "drained": True, "unresolved_attempts": 0},
        {"maintenance": True, "drained": True, "unresolved_attempts": 1},
    ],
)
def test_unknown_or_open_admission_prevents_replacement(client, payload):
    client.setattr(
        state, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode())
    )
    with pytest.raises(RuntimeError, match="Inference is unresolved"):
        state.control("pause")


def test_expected_maintenance_503_is_checked_instead_of_ignored(client):
    def response(*args, **kwargs):
        body = json.dumps({"maintenance": True, "drained": True, "unresolved_attempts": 0}).encode()
        raise HTTPError("http://localhost/health/ready", 503, "maintenance", {}, io.BytesIO(body))

    client.setattr(state, "urlopen", response)
    state.control("paused")


@pytest.mark.parametrize("status", [401, 500])
def test_authentication_and_server_failures_still_fail(client, status):
    def response(*args, **kwargs):
        raise HTTPError("http://localhost/health/ready", status, "failure", {}, io.BytesIO(b"{}"))

    client.setattr(state, "urlopen", response)
    with pytest.raises(HTTPError):
        state.control("paused")
