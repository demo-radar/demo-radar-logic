"""Gem requests share the durable controller without changing the F0 classifier."""

import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from service.app import create_app
from service.config import InferenceConfig
from service.gems.contracts import GemContext
from service.gems.factory import GemFactory
from tests.service.test_api import AUTH, ROOT, completion, live_app, settings

CONTEXT = {
    "external_id": "synthetic-gem",
    "title": "Für sichere Radwege",
    "start_date": "01.11.2026 12:00",
    "end_date": None,
    "raw_address": "Alexanderplatz",
    "raw_zip": "10178",
    "raw_route": "Start - Ziel",
    "current_tags": [],
    "catalog": [{"slug": "mobility", "label": "Mobility"}],
}


def body(root=ROOT):
    config = GemFactory(root).config(InferenceConfig(root))
    return {
        "request_id": "gem-request",
        "job_id": "gem-job",
        "model_id": config.version,
        "source_version": "source-1",
        "input_variant": "GEM-v1",
        "event": {"id": CONTEXT["external_id"], "title": CONTEXT["title"]},
        "context": CONTEXT,
        "execution": {"task": "tagging", "profile_sha256": config.sha256, "origin": "manual_api"},
    }


def test_copy_and_send_share_messages_and_preview_has_no_side_effects(tmp_path):
    app = live_app(tmp_path, lambda request: pytest.fail("Preview must not contact a provider"))
    with TestClient(app) as client:
        for version in ("qwen-v4-v1", "gemini-v4-v1"):
            base = InferenceConfig(ROOT, version)
            config = GemFactory(ROOT).config(base)
            request = {"profile_id": version, "profile_sha256": base.sha256, "context": CONTEXT}
            assert client.post("/v1/gems/tagging/preview", json=request).status_code == 401
            response = client.post("/v1/gems/tagging/preview", json=request, headers=AUTH)
            assert response.status_code == 200
            assert (
                response.json()["messages"]
                == config.payload(GemContext.model_validate(CONTEXT))["messages"]
            )
            assert response.json()["profile"]["profile_sha256"] == config.sha256
            assert "confidence" in response.json()["messages"][0]["content"]
            assert (
                client.post(
                    "/v1/gems/tagging/preview",
                    json={**request, "profile_sha256": "0" * 64},
                    headers=AUTH,
                ).status_code
                == 422
            )
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


def test_synthetic_gem_returns_full_json_and_replays_after_restart(tmp_path):
    runtime = settings(tmp_path)
    with TestClient(create_app(runtime)) as client:
        assert client.post("/v1/gems/tagging", json=body()).status_code == 401
        first = client.post("/v1/gems/tagging", json=body(), headers=AUTH)
        assert first.status_code == 200, first.text
        result = first.json()
        assert result["gem_reply"]["external_id"] == CONTEXT["external_id"]
        assert result["gem_reply"]["tags"] == ["mobility"]
        assert isinstance(result["gem_reply"]["confidence"], float)
        assert result["gem_reply"]["reason"]
        assert result["new_provider_calls"] == 0 and result["requires_staff_review"]
        changed = copy.deepcopy(body())
        changed["context"]["raw_route"] = "Changed route"
        assert client.post("/v1/gems/tagging", json=changed, headers=AUTH).status_code == 409
    with TestClient(create_app(runtime)) as client:
        replay = client.post("/v1/gems/tagging", json=body(), headers=AUTH).json()
        assert replay["replayed"] and replay["gem_reply"] == result["gem_reply"]
        assert replay["statistics"] == result["statistics"]
        assert (
            client.get("/v1/attempts/gem-request", headers=AUTH).json()["gem_reply"]
            == result["gem_reply"]
        )


@pytest.mark.parametrize(
    "change",
    [
        {"input_variant": "F0"},
        {"endpoint": "https://example.com"},
        {
            "execution": {
                "task": "daily-summary",
                "profile_sha256": "0" * 64,
                "origin": "manual_api",
            }
        },
        {"context": {**CONTEXT, "external_id": "different"}},
        {"context": {**CONTEXT, "catalog": [{"slug": "invented", "label": "Invalid"}]}},
    ],
)
def test_invalid_or_unapproved_gem_inputs_are_not_admitted(tmp_path, change):
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        assert (
            client.post("/v1/gems/tagging", json={**body(), **change}, headers=AUTH).status_code
            == 422
        )
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {"external_id": "wrong", "tags": ["mobility"], "confidence": 0.9, "reason": "test"},
        {"external_id": "synthetic-gem", "tags": ["invented"], "confidence": 0.9, "reason": "test"},
    ],
)
def test_live_mocked_gem_retains_usage_but_never_accepts_bad_json(tmp_path, invalid):
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload["messages"][0]["role"] == "system"
        assert json.loads(payload["messages"][1]["content"]) == CONTEXT
        return httpx.Response(
            200,
            json={
                "model": "Qwen/Qwen3.6-35B-A3B-FP8",
                "id": "fixture",
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(invalid)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            },
        )

    app = live_app(tmp_path, handler)
    with TestClient(app) as client:
        response = client.post("/v1/gems/tagging", json=body(), headers=AUTH)
        assert response.status_code == 502, response.text
        assert response.json()["status"] == "failed"
        assert response.json()["gem_reply"] is None
        assert response.json()["statistics"]["total_tokens"] == 25
        assert len(calls) == 1


def test_paid_gemini_gem_uses_system_context_and_shared_spending_controls(tmp_path, monkeypatch):
    from service.providers.models import MODEL_CATALOG, ModelId
    from tests.service.test_gemini import answer, gemini_transport, runtime

    monkeypatch.setitem(MODEL_CATALOG[ModelId.GEMINI_FLASH].pricing, "valid_from", "2000-01-01")
    monkeypatch.setitem(MODEL_CATALOG[ModelId.GEMINI_FLASH].pricing, "valid_until", "2100-12-31")
    replies = []
    expected = {
        "external_id": CONTEXT["external_id"],
        "tags": ["mobility"],
        "confidence": 0.95,
        "reason": "The slogan calls for safer roads.",
    }

    def respond(request):
        native = json.loads(request.content)
        replies.append(native)
        assert (
            "Classify this Berlin demonstration" in native["systemInstruction"]["parts"][0]["text"]
        )
        assert json.loads(native["contents"][-1]["parts"][0]["text"]) == CONTEXT
        assert set(native["generationConfig"]["responseJsonSchema"]["required"]) == set(expected)
        return httpx.Response(200, json=answer(content=json.dumps(expected)))

    config = GemFactory(ROOT).config(InferenceConfig(ROOT, "gemini-v4-v1"))
    data = body()
    data.update(
        model_id=config.version, execution={**data["execution"], "profile_sha256": config.sha256}
    )
    app = create_app(runtime(tmp_path), transport=gemini_transport(respond))
    with TestClient(app) as client:
        response = client.post("/v1/gems/tagging", json=data, headers=AUTH)
        assert response.status_code == 200, response.text
        assert response.json()["gem_reply"] == expected
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT count(*) FROM spending").fetchone()[0] == 1
        replay = client.post("/v1/gems/tagging", json=data, headers=AUTH)
        assert replay.json()["replayed"] and len(replies) == 1


def test_unknown_gem_blocks_new_inference_and_lookup_never_resends(tmp_path):
    calls = []

    def lose_reply(request):
        calls.append(request)
        raise httpx.ReadTimeout("synthetic connection loss", request=request)

    app = live_app(tmp_path, lose_reply)
    with TestClient(app) as client:
        first = client.post("/v1/gems/tagging", json=body(), headers=AUTH)
        assert first.status_code == 504
        assert client.get("/health/ready", headers=AUTH).status_code == 503
        saved = client.get("/v1/attempts/gem-request", headers=AUTH)
        assert saved.json()["status"] == "unknown"
        changed = {**body(), "request_id": "another-request", "job_id": "another-explicit-send"}
        assert client.post("/v1/gems/tagging", json=changed, headers=AUTH).status_code != 200
        assert len(calls) == 1


def test_oversized_gem_is_rejected_before_any_provider_or_journal_attempt(tmp_path):
    app = live_app(tmp_path, lambda request: pytest.fail("Oversized Gem contacted a provider"))
    data = body()
    data["context"] = {
        **CONTEXT,
        "title": "x" * 4000,
        "raw_address": "x" * 4000,
        "raw_route": "x" * 16000,
    }
    data["event"] = {**data["event"], "title": data["context"]["title"]}
    with TestClient(app) as client:
        response = client.post("/v1/gems/tagging", json=data, headers=AUTH)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "gem_input_too_large"
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


@pytest.mark.parametrize(
    "execution", [None, {}, {"origin": "scheduled"}, {"profile_sha256": "0" * 64}]
)
def test_gem_requires_a_manual_execution_and_matching_fingerprint(tmp_path, execution):
    app = live_app(tmp_path, lambda request: pytest.fail("Invalid execution contacted provider"))
    data = body()
    if execution is None:
        data.pop("execution")
    elif execution:
        data["execution"] = {**data["execution"], **execution}
    else:
        data["execution"] = execution
    with TestClient(app) as client:
        response = client.post("/v1/gems/tagging", json=data, headers=AUTH)
        assert response.status_code == 422, response.text
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


def test_manual_sends_accept_tagged_context_after_exhausted_classifier_attempts(tmp_path):
    calls = []
    reply = {
        "external_id": CONTEXT["external_id"],
        "tags": ["mobility"],
        "confidence": 0.8,
        "reason": "The slogan concerns safe cycling.",
    }

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        context = json.loads(payload["messages"][-1]["content"])
        if "catalog" in context:
            assert context["current_tags"] == ["mobility"]
            return httpx.Response(200, json=completion(content=json.dumps(reply)))
        return httpx.Response(200, json=completion(content="invalid JSON"))

    app = live_app(tmp_path, respond)
    with TestClient(app) as client:
        for number in range(4):
            ordinary = {
                "request_id": f"classifier-{number}",
                "job_id": "classifier-job",
                "source_version": body()["source_version"],
                "event": body()["event"],
            }
            response = client.post("/v1/tag-suggestions", json=ordinary, headers=AUTH)
            if number < 3:
                assert response.status_code == 502
            else:
                assert response.json()["error"]["code"] == "event_attempt_limit"
        for number in range(4):
            data = {
                **body(),
                "request_id": f"manual-{number}",
                "job_id": f"send-{number}",
                "context": {**CONTEXT, "current_tags": ["mobility"]},
            }
            response = client.post("/v1/gems/tagging", json=data, headers=AUTH)
            assert response.status_code == 200, response.text
            assert response.json()["statistics"]["attempt_number"] == 1
            saved = app.state.service.journal.execution(data["request_id"])
            assert saved["attempt_limit"] == saved["batch_attempt_limit"] == 1
            replay = client.post("/v1/gems/tagging", json=data, headers=AUTH)
            assert replay.json()["replayed"] and replay.json()["new_provider_calls"] == 0
        assert len(calls) == 7
        # Manual work does not reset the classifier's exhausted allowance.
        ordinary["request_id"] = "classifier-after-manual"
        response = client.post("/v1/tag-suggestions", json=ordinary, headers=AUTH)
        assert response.json()["error"]["code"] == "event_attempt_limit"


def test_manual_job_cannot_retry_failed_generation_with_another_request_id_after_restart(tmp_path):
    calls = []

    def invalid(request):
        calls.append(request)
        return httpx.Response(200, json=completion(content="invalid JSON"))

    with TestClient(live_app(tmp_path, invalid)) as client:
        assert client.post("/v1/gems/tagging", json=body(), headers=AUTH).status_code == 502
    with TestClient(live_app(tmp_path, invalid)) as client:
        changed = {**body(), "request_id": "automatic-retry"}
        denied = client.post("/v1/gems/tagging", json=changed, headers=AUTH)
        assert denied.status_code == 429
        assert denied.json()["error"]["code"] == "event_attempt_limit"
        replay = client.post("/v1/gems/tagging", json=body(), headers=AUTH)
        assert replay.status_code == 502 and replay.json()["replayed"]
        assert len(calls) == 1


def test_fresh_manual_send_keeps_provider_pacing_and_maintenance(tmp_path):
    runtime = settings(tmp_path)
    app = create_app(runtime)
    with TestClient(app) as client:
        assert client.post("/v1/gems/tagging", json=body(), headers=AUTH).status_code == 200
        import time

        with app.state.service.journal.connection() as db:
            db.execute("UPDATE control SET next_allowed=?", (time.time() + 60,))
        fresh = {**body(), "request_id": "fresh-request", "job_id": "fresh-send"}
        paced = client.post("/v1/gems/tagging", json=fresh, headers=AUTH)
        assert paced.status_code == 429 and paced.json()["error"]["code"] == "provider_pacing"
        assert client.post("/v1/maintenance", headers=AUTH).status_code == 200
        paused = client.post("/v1/gems/tagging", json=fresh, headers=AUTH)
        assert paused.status_code == 503 and paused.json()["error"]["code"] == "maintenance"
        assert client.post("/v1/gems/tagging", json=body(), headers=AUTH).json()["replayed"]
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1


def test_fresh_paid_manual_send_keeps_reserved_unknown_usage_under_period_cap(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    from service.providers.models import MODEL_CATALOG, ModelId
    from tests.service.test_gemini import answer, gemini_transport, runtime

    monkeypatch.setitem(MODEL_CATALOG[ModelId.GEMINI_FLASH].pricing, "valid_from", "2000-01-01")
    monkeypatch.setitem(MODEL_CATALOG[ModelId.GEMINI_FLASH].pricing, "valid_until", "2100-12-31")
    calls = []
    reply = {
        "external_id": CONTEXT["external_id"],
        "tags": [],
        "confidence": 0.2,
        "reason": "Synthetic fixture with unknown token usage.",
    }

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=answer(content=json.dumps(reply), usage=False))

    config = GemFactory(ROOT).config(InferenceConfig(ROOT, "gemini-v4-v1"))
    data = {
        **body(),
        "model_id": config.version,
        "execution": {**body()["execution"], "profile_sha256": config.sha256},
    }
    app = create_app(
        replace(runtime(tmp_path), paid_period_usd="0.02"), transport=gemini_transport(respond)
    )
    with TestClient(app) as client:
        first = client.post("/v1/gems/tagging", json=data, headers=AUTH)
        assert first.status_code == 200, first.text
        assert first.json()["statistics"]["total_tokens"] is None
        fresh = {**data, "request_id": "fresh-paid-request", "job_id": "fresh-paid-send"}
        denied = client.post("/v1/gems/tagging", json=fresh, headers=AUTH)
        assert denied.status_code == 429 and denied.json()["error"]["code"] == "spending_limit"
        assert len(calls) == 1
        with app.state.service.journal.connection() as db:
            row = db.execute("SELECT reserved, charged FROM spending").fetchone()
            assert row["reserved"] > 0 and row["charged"] is None
            assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1


def test_closed_unknown_requires_a_fresh_explicit_execution_and_keeps_evidence(
    tmp_path, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    calls = []
    expected = {
        "external_id": CONTEXT["external_id"],
        "tags": [],
        "confidence": 0.1,
        "reason": "The new explicit request completed.",
    }

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(200, json=completion(content=json.dumps(expected)))

    app = live_app(tmp_path, respond)
    with TestClient(app) as client:
        old = client.post("/v1/gems/tagging", json=body(), headers=AUTH).json()
        fresh = {**body(), "request_id": "deliberate-resend", "job_id": "deliberate-new-job"}
        blocked = client.post("/v1/gems/tagging", json=fresh, headers=AUTH)
        assert blocked.json()["error"]["code"] == "inference_busy_or_recovery_required"

        class RecoveryClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz or UTC) + timedelta(minutes=16)

        action = {
            "operator": "admin",
            "reason": "Investigated the synthetic unknown result",
            "accept_unknown_outcome": True,
        }
        with monkeypatch.context() as clock:
            clock.setattr("service.persistence.recovery_store.datetime", RecoveryClock)
            closed = client.post("/v1/attempts/gem-request/close", json=action, headers=AUTH)
            assert closed.status_code == 200, closed.text
        replay = client.post("/v1/gems/tagging", json=body(), headers=AUTH)
        assert replay.status_code == 504 and replay.json()["replayed"]
        assert replay.json()["statistics"] == old["statistics"]
        assert replay.json()["resolution"]["action"] == "abandoned_unknown"
        same_execution = {**body(), "request_id": "blind-retry"}
        denied = client.post("/v1/gems/tagging", json=same_execution, headers=AUTH)
        assert denied.json()["error"]["code"] == "event_outcome_closed_unknown"
        result = client.post("/v1/gems/tagging", json=fresh, headers=AUTH)
        assert result.status_code == 200 and result.json()["gem_reply"] == expected
        assert len(calls) == 2


def test_manual_job_limit_also_covers_attempts_saved_under_an_older_scope(tmp_path, monkeypatch):
    app = live_app(tmp_path, lambda request: httpx.Response(200, json=completion(content="bad")))
    with TestClient(app) as client:
        gem = app.state.gems.services[("tagging", body()["model_id"])]
        # Old Gem implementations keyed attempts by source. Model a persisted
        # older scope, then restart with the execution-scoped implementation.
        monkeypatch.setattr(gem, "attempt_key", lambda request: "old-source-key")
        monkeypatch.setattr(gem, "allowance_key", lambda request: "old-source-allowance")
        assert client.post("/v1/gems/tagging", json=body(), headers=AUTH).status_code == 502
    app = live_app(tmp_path, lambda request: pytest.fail("An existing execution was retried"))
    with TestClient(app) as client:
        retry = {**body(), "request_id": "new-key-old-job"}
        denied = client.post("/v1/gems/tagging", json=retry, headers=AUTH)
        assert denied.status_code == 429 and denied.json()["error"]["code"] == "batch_limit"


@pytest.mark.parametrize(
    ("returned_model", "expected_status"),
    [
        ("Qwen/Qwen3.6-35B-A3B-FP8", 200),
        ("Qwen/Qwen3.6-35B-A3B", 200),
        ("another-model", 502),
    ],
)
def test_gem_accepts_only_approved_returned_model_names(tmp_path, returned_model, expected_status):
    """Hetzner reports its deployed Qwen name without the requested FP8 suffix."""
    calls = []
    expected = {
        "external_id": CONTEXT["external_id"],
        "tags": ["mobility"],
        "confidence": 0.95,
        "reason": "The slogan calls for safer roads.",
    }

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "model": returned_model,
                "id": "fixture-model-alias",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(expected)}}
                ],
                "usage": {"prompt_tokens": 481, "completion_tokens": 132, "total_tokens": 613},
            },
        )

    app = live_app(tmp_path, handler)
    with TestClient(app) as client:
        response = client.post("/v1/gems/tagging", json=body(), headers=AUTH)
        assert response.status_code == expected_status, response.text
        result = response.json()
        assert result["statistics"]["returned_model"] == returned_model
        assert result["statistics"]["total_tokens"] == 613
        if expected_status == 200:
            assert result["gem_reply"] == expected
        else:
            assert result["error"]["code"] == "gem_model_mismatch"
            assert result["gem_reply"] is None
        saved = client.get("/v1/attempts/gem-request", headers=AUTH)
        assert saved.json()["statistics"] == result["statistics"]
        assert len(calls) == 1


def test_gem_factory_rejects_changed_assets_and_unknown_versions(tmp_path):
    """A version name alone cannot authorize changed instructions."""
    import shutil

    shutil.copytree(ROOT / "configs/gems", tmp_path / "configs/gems")
    factory = GemFactory(tmp_path)
    definition = factory.definition()
    assert definition.version == "tagging-gem-v1"
    assert definition.limits.max_attempts == definition.limits.max_job_attempts == 1
    with pytest.raises(ValueError, match="Unsupported Gem version"):
        factory.definition("unapproved-gem")
    asset = tmp_path / "configs/gems/tagging-v1.json"
    data = json.loads(asset.read_text())
    data["system"][0] = "Changed instructions"
    asset.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="fingerprint"):
        factory.definition()
