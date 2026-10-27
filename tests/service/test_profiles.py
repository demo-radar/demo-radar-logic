"""Offline profiles, immutable admission, recovery and rollback compatibility."""

import hashlib
import json
import shutil
import sqlite3
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from service.app import create_app
from service.config import InferenceConfig
from service.inference.results import fingerprint
from service.providers.base import ProviderResult
from tests.service.test_api import AUTH, ROOT, request, settings

ALTERNATE = "synthetic-retained-v1"


def profile_root(tmp_path):
    """Register a second invented profile only inside this disposable test root."""
    target = tmp_path / "assets"
    shutil.copytree(ROOT / "configs", target / "configs")
    rubric = target / "docs/rubrics/tagging-rubric-v4.md"
    rubric.parent.mkdir(parents=True)
    rubric.write_bytes((ROOT / "docs/rubrics/tagging-rubric-v4.md").read_bytes())
    directory = target / "configs/inference"
    config = json.loads((directory / "qwen-v4-v1.json").read_text())
    config["version"] = ALTERNATE
    raw = json.dumps(config).encode()
    (directory / (ALTERNATE + ".json")).write_bytes(raw)
    catalog = json.loads((directory / "catalog.json").read_text())
    catalog["configurations"][ALTERNATE] = {
        **catalog["configurations"]["qwen-v4-v1"],
        "path": "configs/inference/" + ALTERNATE + ".json",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    (directory / "catalog.json").write_text(json.dumps(catalog))
    return target


def explicit_request(number=1):
    value = request(number)
    value["execution"] = {
        "task": "tagging",
        "profile_sha256": InferenceConfig(ROOT).sha256,
        "origin": "manual_api",
    }
    return value


def test_catalog_is_authenticated_read_only_and_routes_stay_disabled(tmp_path):
    with TestClient(create_app(settings(tmp_path, summary_enabled=True))) as client:
        assert client.get("/v1/task-profiles").status_code == 401
        response = client.get("/v1/task-profiles", headers=AUTH)
        data = response.json()
        assert data["unavailable_tasks"] == ["routes"]
        assert {p["task"] for p in data["profiles"]} == {"tagging", "daily-summary"}
        assert all(p["enabled"] for p in data["profiles"])
        assert "system" not in response.text and "synthetic-test-token" not in response.text
        assert client.post("/v1/task-profiles", json={}, headers=AUTH).status_code == 405
        assert client.post("/v1/route-suggestions", json={}, headers=AUTH).status_code == 404
        for change in (
            {"task": "routes"},
            {"task": "daily-summary"},
            {"profile_sha256": "0" * 64},
            {"endpoint": "https://example.com"},
        ):
            body = explicit_request()
            body["execution"].update(change)
            rejected = client.post("/v1/tag-suggestions", json=body, headers=AUTH)
            assert rejected.status_code == 422
            assert rejected.json()["inference_admitted"] is False
        assert client.app.state.service.journal.maintenance()["drained"]


def test_context_is_saved_before_execution_and_never_contains_source_or_secrets(tmp_path, caplog):
    app = create_app(settings(tmp_path, environment="test"))
    with TestClient(app) as client:
        original = app.state.service.provider

        class InspectProvider:
            async def predict(self, payload):
                context = app.state.service.journal.execution("request-1")
                assert context["origin"] == "manual_api"
                assert context["environment"] == "test"
                assert context["execution_started_at"]
                assert context["payload_sha256"] == fingerprint(payload)
                return await original.predict(payload)

        app.state.service.provider = InspectProvider()
        with caplog.at_level("INFO", logger="service.inference.coordinator"):
            first = client.post("/v1/tag-suggestions", json=explicit_request(), headers=AUTH).json()
        context = client.get("/v1/attempts/request-1/execution", headers=AUTH).json()
        assert context["maximum_output_tokens"] == 4096
        assert context["attempt_limit"] == 3 and context["provider_seconds"] >= 0
        assert context["profile_sha256"] == first["config_sha256"]
        assert first["statistics"]["total_tokens"] is None
        assert "Für sichere" not in json.dumps(context) + caplog.text
        assert "synthetic-test-token" not in json.dumps(context) + caplog.text
        assert "phase=saved" in caplog.text
        with app.state.service.journal.connection() as db, pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE attempt_execution SET snapshot='{}'")
        assert client.get("/v1/attempts/request-1/execution").status_code == 401


def test_restart_retains_pinned_profile_and_retired_results_still_replay(tmp_path):
    assets = profile_root(tmp_path)
    runtime = settings(tmp_path, root=assets)
    with TestClient(create_app(runtime)) as client:
        first = client.post("/v1/tag-suggestions", json=request(), headers=AUTH).json()
    newer = replace(runtime, config_id=ALTERNATE, retained_tag_configs=("qwen-v4-v1",))
    with TestClient(create_app(newer)) as client:
        profiles = client.get("/v1/task-profiles", headers=AUTH).json()["profiles"]
        assert {p["profile_id"] for p in profiles} == {"qwen-v4-v1", ALTERNATE, "gemini-v4-v1"}
        second = request(2)
        assert client.post("/v1/tag-suggestions", json=second, headers=AUTH).status_code == 200
    with TestClient(create_app(replace(newer, retained_tag_configs=()))) as client:
        replay = client.post("/v1/tag-suggestions", json=request(), headers=AUTH).json()
        assert replay["replayed"] and replay["statistics"] == first["statistics"]
        assert replay["new_provider_calls"] == 0
        assert client.get("/v1/attempts/request-1/execution", headers=AUTH).status_code == 200
        assert client.post("/v1/tag-suggestions", json=request(3), headers=AUTH).status_code == 422
        altered = request(title="Different source")
        assert client.post("/v1/tag-suggestions", json=altered, headers=AUTH).status_code == 409
        assert client.get("/health/ready", headers=AUTH).status_code == 200


def test_legacy_identity_and_old_journal_remain_compatible(tmp_path):
    runtime = settings(tmp_path)
    data = request()
    with TestClient(create_app(runtime)) as client:
        first = client.post("/v1/tag-suggestions", json=data, headers=AUTH).json()
        with client.app.state.service.journal.connection() as db:
            identity = db.execute("SELECT identity FROM attempts").fetchone()[0]
            expected = fingerprint(
                {
                    "request": {
                        **data,
                        "model_id": "qwen-v4-v1",
                        "taxonomy_version": "v2",
                        "input_variant": "F0",
                    },
                    "config": first["config_sha256"],
                    "mode": "demo",
                }
            )
            assert identity == expected
            # Simulate a genuine pre-context journal without rewriting its saved answer.
            db.execute("DELETE FROM attempt_execution")
    with TestClient(create_app(runtime)) as client:
        replay = client.post("/v1/tag-suggestions", json=data, headers=AUTH).json()
        assert replay["statistics"] == first["statistics"]
        assert replay["replayed"]
    # Legacy SQL still sees the original nine columns and version after migration.
    with sqlite3.connect(runtime.database) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert len(db.execute("SELECT * FROM attempts").description) == 9
        assert (
            json.loads(db.execute("SELECT result FROM attempts").fetchone()[0])["statistics"]
            == first["statistics"]
        )


def test_profile_changes_do_not_reset_attempts_or_unknown_outcomes(tmp_path):
    assets = profile_root(tmp_path)
    for unknown in (False, True):
        folder = tmp_path / str(unknown)
        runtime = settings(
            folder,
            root=assets,
            max_attempts_per_event=1,
            mode="live",
            provider_key="fake",
            free_tier_confirmed=True,
        )
        calls = []

        def handler(req, calls=calls, unknown=unknown):
            calls.append(req)
            if unknown:
                raise httpx.ReadTimeout("synthetic lost response")
            return httpx.Response(400, json={})

        with TestClient(create_app(runtime, transport=httpx.MockTransport(handler))) as client:
            assert (
                client.post("/v1/tag-suggestions", json=request(), headers=AUTH).status_code >= 400
            )
        changed = replace(runtime, config_id=ALTERNATE)
        with TestClient(create_app(changed, transport=httpx.MockTransport(handler))) as client:
            body = request()
            body.update(request_id="another-attempt", job_id="another-job", model_id=ALTERNATE)
            result = client.post("/v1/tag-suggestions", json=body, headers=AUTH)
            expected = "inference_busy_or_recovery_required" if unknown else "event_attempt_limit"
            assert result.json()["error"]["code"] == expected
            assert len(calls) == 1


def test_a_job_cannot_change_profile_and_malformed_adapter_output_is_a_saved_failure(tmp_path):
    assets = profile_root(tmp_path)
    runtime = settings(tmp_path, root=assets, retained_tag_configs=(ALTERNATE,))
    with TestClient(create_app(runtime)) as client:

        class InvalidProvider:
            async def predict(self, payload):
                return ProviderResult(
                    ["made-up-tag"], {"model": "synthetic", "usage": {"total_tokens": 17}}
                )

        client.app.state.service.provider = InvalidProvider()
        invalid = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        assert invalid.json()["status"] == "failed"
        assert invalid.json()["statistics"]["total_tokens"] == 17
        assert invalid.json()["error"]["code"] == "invalid_provider_response"
        assert client.app.state.service.journal.maintenance()["drained"]
        changed = {**request(2), "model_id": ALTERNATE}
        result = client.post("/v1/tag-suggestions", json=changed, headers=AUTH)
        assert result.json()["error"]["code"] == "job_configuration_mismatch"


def test_summary_uses_same_profile_catalog_and_shared_private_context(tmp_path):
    from tests.service.summary.test_api import request as summary_request

    runtime = settings(tmp_path, summary_enabled=True, environment="test")
    body = summary_request()
    body["execution"] = {
        "task": "daily-summary",
        "origin": "scheduled",
        "profile_sha256": body["config_sha256"],
    }
    with TestClient(create_app(runtime)) as client:
        result = client.post("/v1/daily-summary-drafts", json=body, headers=AUTH)
        assert result.status_code == 200
        context = client.get("/v1/attempts/daily-one/execution", headers=AUTH).json()
        assert context["task"] == "daily-summary" and context["origin"] == "scheduled"
        assert context["source_sha256"] == body["snapshot_sha256"]
        assert context["example_sha256"] and context["provider_seconds"] >= 0
        assert client.post("/v1/daily-summary-drafts", json=body, headers=AUTH).json()["replayed"]
        assert (
            client.post(
                "/v1/tag-suggestions", json={**request(), "request_id": "daily-one"}, headers=AUTH
            ).status_code
            == 409
        )


def test_backfilled_failed_attempts_keep_the_allowance_across_profile_changes(tmp_path):
    assets = profile_root(tmp_path)
    runtime = settings(
        tmp_path,
        root=assets,
        max_attempts_per_event=1,
        mode="live",
        provider_key="fake",
        free_tier_confirmed=True,
    )
    with TestClient(
        create_app(runtime, transport=httpx.MockTransport(lambda req: httpx.Response(400, json={})))
    ) as client:
        client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        with client.app.state.service.journal.connection() as db:
            db.execute("DELETE FROM attempt_execution")
    with TestClient(create_app(replace(runtime, config_id=ALTERNATE))) as client:
        old = client.get("/v1/attempts/request-1/execution", headers=AUTH).json()
        assert old["evidence"] == "legacy-result"
        assert old["provider_seconds"] is None and old["environment"] == "unspecified"
        new = {**request(), "request_id": "new", "job_id": "new", "model_id": ALTERNATE}
        result = client.post("/v1/tag-suggestions", json=new, headers=AUTH)
        assert result.json()["error"]["code"] == "event_attempt_limit"


def test_retained_summary_configuration_executes_and_retired_one_only_replays(tmp_path):
    from service.summary.config import SummaryConfig
    from tests.service.summary.test_api import request as summary_request

    runtime = settings(tmp_path, summary_enabled=True, retained_summary_configs=("qwen-daily-v7",))
    data = summary_request()
    data.update(model_id="qwen-daily-v7", config_sha256=SummaryConfig(ROOT, "qwen-daily-v7").sha256)
    with TestClient(create_app(runtime)) as client:
        response = client.post("/v1/daily-summary-drafts", json=data, headers=AUTH)
        assert response.status_code == 200
        first = response.json()
        assert first["config_version"] == "qwen-daily-v7"
    with TestClient(create_app(replace(runtime, retained_summary_configs=()))) as client:
        replay = client.post("/v1/daily-summary-drafts", json=data, headers=AUTH).json()
        assert replay["replayed"] and replay["statistics"] == first["statistics"]
        data["request_id"] = "fresh-retired-request"
        assert client.post("/v1/daily-summary-drafts", json=data, headers=AUTH).status_code == 422


def test_renamed_summary_profile_preserves_the_legacy_contract_identity():
    from service.summary.config import SummaryConfig

    current = SummaryConfig(ROOT, "hetzner-daily-v1")
    legacy = SummaryConfig(ROOT, "daily-summary-v1")
    assert current.version == "hetzner-daily-v1"
    assert legacy.version == "daily-summary-v1"
    assert current.sha256 == legacy.sha256
    assert current.data == legacy.data
