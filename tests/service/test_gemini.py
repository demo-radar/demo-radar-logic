"""Offline Gemini checks: strict outputs, retained evidence and monetary admission."""

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from service.app import create_app
from service.config import InferenceConfig
from service.persistence import spending
from service.persistence.journal import AdmissionError, Journal
from service.providers.gemini import GeminiProvider
from service.providers.models import MODEL_CATALOG, ModelDefinition, ModelId
from tests.service.summary.test_api import request as summary_request
from tests.service.test_api import AUTH, request, settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def reviewed_price(monkeypatch):
    # Clock-independent fixtures; the expiration test exercises the real cutoff rule.
    monkeypatch.setitem(MODEL_CATALOG[ModelId.GEMINI_FLASH].pricing, "valid_from", "2000-01-01")
    monkeypatch.setitem(MODEL_CATALOG[ModelId.GEMINI_FLASH].pricing, "valid_until", "2100-12-31")


def runtime(tmp_path, **changes):
    return settings(
        tmp_path,
        mode="live",
        provider_key="synthetic-hetzner-secret",
        free_tier_confirmed=True,
        gemini_key="synthetic-gemini-secret",
        gemini_enabled=True,
        paid_account="synthetic-account",
        paid_run_usd="10",
        paid_period_usd="20",
        paid_account_usd="20",
        summary_enabled=True,
        **changes,
    )


def gemini_transport(handler):
    def respond(request):
        if request.url.path.endswith(":countTokens"):
            assert request.headers["x-goog-api-key"] == "synthetic-gemini-secret"
            body = json.loads(request.content)["generateContentRequest"]
            assert body["model"] == "models/gemini-3.8-flash"
            assert "systemInstruction" in body and "generationConfig" in body
            return httpx.Response(200, json={"totalTokens": 10})
        return handler(request)

    return httpx.MockTransport(respond)


def answer(tags=None, *, content=None, finish="STOP", usage=True):
    body = {
        "modelVersion": ModelId.GEMINI_FLASH,
        "responseId": "synthetic-provider-id",
        "candidates": [
            {
                "finishReason": finish,
                "content": {"parts": [{"text": content or json.dumps({"tags": tags or []})}]},
            }
        ],
    }
    if usage:
        body["usageMetadata"] = {
            "promptTokenCount": 10,
            "candidatesTokenCount": 3,
            "thoughtsTokenCount": 2,
            "totalTokenCount": 15,
            "cachedContentTokenCount": 4,
        }
    return body


def gemini_request(n=1, **changes):
    data = request(n)
    data["model_id"] = "gemini-v4-v1"
    data.update(changes)
    return data


def test_profiles_are_independent_and_disabled_without_operator_approval(tmp_path):
    calls = []

    def response(req):
        calls.append(req)
        return httpx.Response(200, json=answer(["mobility"]))

    with TestClient(
        create_app(
            replace(runtime(tmp_path), gemini_enabled=False), transport=gemini_transport(response)
        )
    ) as client:
        profiles = client.get("/v1/task-profiles", headers=AUTH).json()["profiles"]
        assert {(p["task"], p["provider"]) for p in profiles} == {
            ("tagging", "hetzner"),
            ("daily-summary", "hetzner"),
            ("tagging", "gemini"),
            ("daily-summary", "gemini"),
        }
        assert all(not p["enabled"] for p in profiles if p["provider"] == "gemini")
        denied = client.post("/v1/tag-suggestions", json=gemini_request(), headers=AUTH)
        assert denied.status_code == 503 and denied.json()["inference_admitted"] is False
        assert not calls


def test_native_request_and_usage_are_normalized_once(tmp_path):
    calls = []

    def response(req):
        calls.append(req)
        assert req.headers["x-goog-api-key"] == "synthetic-gemini-secret"
        assert "key=" not in str(req.url)
        payload = json.loads(req.content)
        assert set(payload) == {"contents", "systemInstruction", "generationConfig"}
        assert payload["generationConfig"]["maxOutputTokens"] == 4096
        assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
        return httpx.Response(200, json=answer(["mobility"]))

    app = create_app(runtime(tmp_path), transport=gemini_transport(response))
    with TestClient(app) as client:
        first = client.post("/v1/tag-suggestions", json=gemini_request(), headers=AUTH)
        assert first.status_code == 200, first.text
        stats = first.json()["statistics"]
        assert (
            stats["input_tokens"],
            stats["output_tokens"],
            stats["total_tokens"],
            stats["reasoning_tokens"],
        ) == (10, 5, 15, 2)
        assert stats["usage_raw"]["gemini"]["thoughtsTokenCount"] == 2
        repeated = client.post("/v1/tag-suggestions", json=gemini_request(), headers=AUTH).json()
        assert repeated["replayed"] and repeated["statistics"] == stats and len(calls) == 1
        with app.state.service.journal.connection() as db:
            row = db.execute("SELECT * FROM spending").fetchone()
            assert row["charged"] == 27 and row["reserved"] == 16136


@pytest.mark.parametrize(
    "change",
    [
        {"finish": "MAX_TOKENS"},
        {"content": "not json"},
        {"content": '{"tags":["unknown"]}'},
        {"content": '{"tags":["mobility","mobility"]}'},
    ],
)
def test_bad_output_retains_known_usage(tmp_path, change):
    app = create_app(
        runtime(tmp_path),
        transport=gemini_transport(lambda _: httpx.Response(200, json=answer(**change))),
    )
    with TestClient(app) as client:
        reply = client.post("/v1/tag-suggestions", json=gemini_request(), headers=AUTH)
        assert reply.status_code == 502 and reply.json()["statistics"]["total_tokens"] == 15
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT charged FROM spending").fetchone()[0] == 27


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("paid_run_usd", "", "spending_not_configured"),
        ("paid_period_usd", "0", "spending_not_configured"),
        ("paid_account", "", "spending_not_configured"),
        ("paid_run_usd", "NaN", "spending_not_configured"),
        ("paid_run_usd", "1e999999999", "spending_not_configured"),
        ("paid_account_usd", "0.01", "spending_limit"),
        ("paid_period_usd", "0.01", "spending_limit"),
        ("paid_run_usd", "0.016135", "spending_limit"),
    ],
)
def test_paid_refusals_happen_before_generation_and_reservation(tmp_path, field, value, code):
    calls = []
    app = create_app(
        replace(runtime(tmp_path), **{field: value}),
        transport=gemini_transport(lambda req: calls.append(req)),
    )
    with TestClient(app) as client:
        result = client.post("/v1/tag-suggestions", json=gemini_request(), headers=AUTH).json()
        assert result["error"]["code"] == code and result["inference_admitted"] is False
        assert not calls
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM spending").fetchone()[0] == 0


def test_exact_limit_missing_usage_and_restart_share_daily_allowance(tmp_path):
    config = replace(runtime(tmp_path), paid_period_usd="0.016136")
    calls = []

    def response(req):
        calls.append(req)
        return httpx.Response(200, json=answer(usage=False))

    for attempt in (1, 2):
        with TestClient(create_app(config, transport=gemini_transport(response))) as client:
            result = client.post("/v1/tag-suggestions", json=gemini_request(attempt), headers=AUTH)
            if attempt == 1:
                assert result.status_code == 200, result.text
                assert result.json()["statistics"]["input_tokens"] is None
            else:
                assert result.json()["error"]["code"] == "spending_limit"
    assert len(calls) == 1
    with Journal(config.database).connection() as db:
        row = db.execute("SELECT * FROM spending").fetchone()
        assert row["charged"] is None and row["reserved"] == 16136


def test_expired_price_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setitem(MODEL_CATALOG[ModelId.GEMINI_FLASH].pricing, "valid_until", "2001-01-01")
    with pytest.raises(AdmissionError, match=None) as exc:
        spending.policy(runtime(tmp_path), InferenceConfig(ROOT, "gemini-v4-v1"))
    assert exc.value.code == "pricing_review_required"


def test_gemini_summary_uses_same_example_schema_and_spending_guard(tmp_path):
    from service.summary.config import SummaryConfig

    config = SummaryConfig(ROOT, "gemini-daily-v1")
    data = summary_request()
    data.update(model_id=config.version, config_sha256=config.sha256)
    draft = {
        "overview": [{"text": "Eine Aktion fordert sichere Radwege.", "event_ids": ["d001"]}],
        "topics": [{"label": "Mobilität", "text": "Sichere Radwege.", "event_ids": ["d001"]}],
        "highlight": None,
        "limitations": ["Nur angemeldete Versammlungen."],
    }
    calls = []

    def response(req):
        calls.append(req)
        payload = json.loads(req.content)
        assert [part["role"] for part in payload["contents"]] == ["user", "model", "user"]
        assert "responseJsonSchema" in payload["generationConfig"]
        return httpx.Response(200, json=answer(content=json.dumps(draft)))

    with TestClient(create_app(runtime(tmp_path), transport=gemini_transport(response))) as client:
        reply = client.post("/v1/daily-summary-drafts", headers=AUTH, json=data)
        assert reply.status_code == 200, reply.text
        assert reply.json()["statistics"]["provider"] == "gemini" and len(calls) == 1


@pytest.mark.parametrize("outcome", ["timeout", "rate_limit", "server_error", "malformed_envelope"])
def test_failures_keep_reservations_and_do_not_retry(tmp_path, outcome):
    calls = []

    def response(req):
        calls.append(req)
        if outcome == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=req)
        if outcome == "rate_limit":
            return httpx.Response(429, headers={"Retry-After": "5"})
        if outcome == "server_error":
            return httpx.Response(503)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [7]}}]})

    config = runtime(tmp_path)
    with TestClient(create_app(config, transport=gemini_transport(response))) as client:
        reply = client.post("/v1/tag-suggestions", headers=AUTH, json=gemini_request())
        assert reply.status_code in {429, 502, 504}, reply.text
        assert len(calls) == 1
        saved = client.get("/v1/attempts/request-1/spending", headers=AUTH).json()
        assert saved["awaiting_reconciliation"] and saved["reserved_microusd"] == 16136
        assert client.get("/v1/attempts/request-1/spending").status_code == 401
    with Journal(config.database).connection() as db:
        assert db.execute("SELECT charged FROM spending").fetchone()[0] is None


def test_paid_run_and_shared_period_count_retries_and_other_tasks(tmp_path):
    from service.summary.config import SummaryConfig

    calls = []

    def response(req):
        calls.append(req)
        return httpx.Response(200, json=answer(content="bad json", usage=False))

    config = replace(runtime(tmp_path), paid_run_usd="0.016136", paid_period_usd="0.016136")
    with TestClient(create_app(config, transport=gemini_transport(response))) as client:
        first = gemini_request()
        assert client.post("/v1/tag-suggestions", headers=AUTH, json=first).status_code == 502
        retry = {**first, "request_id": "explicit-retry"}
        assert (
            client.post("/v1/tag-suggestions", headers=AUTH, json=retry).json()["error"]["code"]
            == "spending_limit"
        )
        summary = summary_request()
        profile = SummaryConfig(ROOT, "gemini-daily-v1")
        summary.update(
            model_id=profile.version,
            config_sha256=profile.sha256,
            execution={
                "task": "daily-summary",
                "profile_sha256": profile.sha256,
                "origin": "scheduled",
            },
        )
        assert (
            client.post("/v1/daily-summary-drafts", headers=AUTH, json=summary).json()["error"][
                "code"
            ]
            == "spending_limit"
        )
        assert len(calls) == 1


def test_unknown_closure_does_not_release_money_and_settlement_is_audited(tmp_path):
    from datetime import UTC, datetime, timedelta

    config = runtime(tmp_path)

    def response(req):
        raise httpx.ReadTimeout("synthetic timeout", request=req)

    app = create_app(config, transport=gemini_transport(response))
    with TestClient(app) as client:
        result = client.post("/v1/tag-suggestions", headers=AUTH, json=gemini_request()).json()
        evidence = {
            "amount_usd": "0.000027",
            "operator": "test-operator",
            "reason": "Verified the synthetic account usage record.",
            "verified_account_evidence": True,
        }
        path = "/v1/attempts/request-1/spending"
        assert client.post(path, headers=AUTH, json=evidence).status_code == 409
        result["statistics"]["finished_at"] = (
            datetime.now(UTC) - timedelta(minutes=16)
        ).isoformat()
        with app.state.service.journal.connection() as db:
            db.execute(
                "UPDATE attempts SET result=? WHERE request_id=?", (json.dumps(result), "request-1")
            )
        closed = client.post(
            "/v1/attempts/request-1/close",
            headers=AUTH,
            json={
                "operator": "test-operator",
                "reason": "Confirmed no active local worker; accept uncertainty.",
                "accept_unknown_outcome": True,
            },
        )
        assert closed.status_code == 200, closed.text
        assert client.get(path, headers=AUTH).json()["awaiting_reconciliation"]
        settled = client.post(path, headers=AUTH, json=evidence)
        assert settled.status_code == 200 and settled.json()["charged_microusd"] == 27
        assert client.post(path, headers=AUTH, json=evidence).status_code == 200
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM spending_audit").fetchone()[0] == 1
            assert db.execute("SELECT status FROM attempts").fetchone()[0] == "unknown"


def test_crash_marker_keeps_paid_reservation_and_cannot_be_settled(tmp_path):
    from service.contracts import TagRequest

    config = runtime(tmp_path)
    profile = InferenceConfig(ROOT, "gemini-v4-v1")
    journal = Journal(config.database)
    data = TagRequest.model_validate(gemini_request())
    journal.begin(data, "identity", "event", 0, spending=spending.policy(config, profile))
    restarted = Journal(config.database)
    with restarted.connection() as db:
        assert spending.inspect(db, data.request_id)["awaiting_reconciliation"]
        with pytest.raises(AdmissionError) as exc:
            spending.settle(
                db, data.request_id, "0", "test-operator", "Investigated synthetic crash"
            )
        assert exc.value.code == "attempt_unresolved"
    with pytest.raises(AdmissionError) as exc:
        restarted.begin(
            TagRequest.model_validate(gemini_request(2)),
            "next",
            "other",
            0,
            spending=spending.policy(config, profile),
        )
    assert exc.value.code == "inference_busy_or_recovery_required"


def test_atomic_reservations_cannot_overspend_concurrently(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from service.contracts import TagRequest

    config = replace(runtime(tmp_path), paid_period_usd="1.032192")
    journal = Journal(config.database)
    approved = spending.policy(config, InferenceConfig(ROOT, "gemini-v4-v1"))

    def reserve(number):
        try:
            journal.begin(
                TagRequest.model_validate(gemini_request(number)),
                str(number),
                str(number),
                0,
                spending=approved,
            )
            return "reserved"
        except AdmissionError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, [1, 2]))
    assert outcomes.count("reserved") == 1
    with journal.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM spending").fetchone()[0] == 1


def test_unknown_reservation_carries_over_midnight_but_known_charges_reset(tmp_path):
    from service.contracts import TagRequest

    config = replace(runtime(tmp_path), paid_period_usd="1.032192")
    journal = Journal(config.database)
    approved = spending.policy(config, InferenceConfig(ROOT, "gemini-v4-v1"))
    data = TagRequest.model_validate(gemini_request())
    journal.begin(data, "first", "first-event", 0, spending=approved)
    # Simulate a completed answer with unknown usage from the previous UTC period.
    with journal.connection() as db:
        db.execute("UPDATE spending SET period='2000-01-01'")
        tomorrow = {**approved, "period": "2100-01-01"}
        with pytest.raises(AdmissionError) as exc:
            spending.reserve(db, TagRequest.model_validate(gemini_request(2)), tomorrow)
        assert exc.value.code == "spending_limit"
        db.execute("UPDATE spending SET charged=27")
        # No real second call: this checks allowance calculation in a rolled-back transaction.
        db.execute(
            "INSERT INTO attempts VALUES('request-2','i','e','event','job','ok','{}',200,'2000-01-01')"
        )
        spending.reserve(db, TagRequest.model_validate(gemini_request(2)), tomorrow)
        assert db.execute("SELECT COUNT(*) FROM spending").fetchone()[0] == 2


@pytest.mark.parametrize("tag_provider", ["gemini", "hetzner"])
def test_mixed_tagging_and_summary_providers_in_both_directions(tmp_path, tag_provider):
    from service.summary.config import SummaryConfig

    qwen = "Qwen/Qwen3.6-35B-A3B-FP8"
    draft = {
        "overview": [{"text": "Eine Aktion fordert sichere Radwege.", "event_ids": ["d001"]}],
        "topics": [{"label": "Mobilität", "text": "Sichere Radwege.", "event_ids": ["d001"]}],
        "highlight": None,
        "limitations": ["Nur angemeldete Versammlungen."],
    }
    seen = []

    def response(req):
        seen.append(req.url.host)
        payload = json.loads(req.content)
        native = req.url.host == "generativelanguage.googleapis.com"
        cap = (
            payload["generationConfig"]["maxOutputTokens"]
            if native
            else payload["max_completion_tokens"]
        )
        text = json.dumps(draft if cap == 8192 else {"tags": ["mobility"]})
        return httpx.Response(
            200,
            json=answer(content=text)
            if native
            else {
                "model": qwen,
                "id": "synthetic-qwen-id",
                "choices": [{"finish_reason": "stop", "message": {"content": text}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    summary_config = SummaryConfig(
        ROOT, "hetzner-daily-v1" if tag_provider == "gemini" else "gemini-daily-v1"
    )
    tag = gemini_request() if tag_provider == "gemini" else request()
    summary = summary_request()
    summary.update(model_id=summary_config.version, config_sha256=summary_config.sha256)
    app = create_app(runtime(tmp_path), transport=gemini_transport(response))
    with TestClient(app) as client:
        tag_result = client.post("/v1/tag-suggestions", json=tag, headers=AUTH)
        summary_result = client.post("/v1/daily-summary-drafts", json=summary, headers=AUTH)
        assert tag_result.status_code == summary_result.status_code == 200, summary_result.text
        assert tag_result.json()["statistics"]["provider"] == tag_provider
        assert summary_result.json()["statistics"]["provider"] != tag_provider
        assert len(seen) == 2 and len(set(seen)) == 2
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM spending").fetchone()[0] == 1


def test_switching_profile_cannot_reset_event_attempt_allowance(tmp_path):
    config = replace(runtime(tmp_path), max_attempts_per_event=1)

    def response(req):
        return httpx.Response(
            200,
            json={
                "model": "Qwen/Qwen3.6-35B-A3B-FP8",
                "choices": [{"finish_reason": "stop", "message": {"content": "invalid"}}],
            },
        )

    with TestClient(create_app(config, transport=gemini_transport(response))) as client:
        original = request()
        assert client.post("/v1/tag-suggestions", headers=AUTH, json=original).status_code == 502
        switched = {
            **original,
            "request_id": "second-id",
            "job_id": "another-job",
            "model_id": "gemini-v4-v1",
        }
        denied = client.post("/v1/tag-suggestions", headers=AUTH, json=switched)
        assert denied.json()["error"]["code"] == "event_attempt_limit"
        assert denied.json()["inference_admitted"] is False


def test_unexpected_model_usage_pauses_paid_calls_until_audited(tmp_path):
    config = runtime(tmp_path)
    calls = []

    def response(req):
        calls.append(req)
        body = answer()
        body["modelVersion"] = "unexpected-model"
        return httpx.Response(200, json=body)

    app = create_app(config, transport=gemini_transport(response))
    with TestClient(app) as client:
        assert (
            client.post("/v1/tag-suggestions", headers=AUTH, json=gemini_request()).status_code
            == 502
        )
        evidence = client.get("/v1/attempts/request-1/spending", headers=AUTH).json()
        assert evidence["awaiting_reconciliation"] and evidence["review_required"]
        denied = client.post("/v1/tag-suggestions", headers=AUTH, json=gemini_request(2))
        assert denied.json()["error"]["code"] == "spending_review_required" and len(calls) == 1
        settled = client.post(
            "/v1/attempts/request-1/spending",
            headers=AUTH,
            json={
                "amount_usd": "0.000100",
                "operator": "test-operator",
                "reason": "Verified synthetic account charge for the unexpected model.",
                "verified_account_evidence": True,
            },
        )
        assert settled.status_code == 200 and not settled.json()["review_required"]


def test_four_events_fit_small_budget_and_replay_skips_token_count(tmp_path):
    calls = []

    def response(req):
        calls.append(req.url.path)
        body = json.loads(req.content)
        if req.url.path.endswith(":countTokens"):
            native = body["generateContentRequest"]
            assert (
                json.loads(native["contents"][-1]["parts"][-1]["text"])
                == native["generationConfig"]
            )
            return httpx.Response(200, json={"totalTokens": 20000})
        assert len(body["contents"][-1]["parts"]) == 1
        return httpx.Response(200, json=answer(["mobility"]))

    config = replace(
        runtime(tmp_path), paid_run_usd="0.32", paid_period_usd="0.32", paid_account_usd="0.32"
    )
    app = create_app(config, transport=httpx.MockTransport(response))
    with TestClient(app) as client:
        for number in range(1, 5):
            data = gemini_request(number)
            first = client.post("/v1/tag-suggestions", json=data, headers=AUTH)
            assert first.status_code == 200, first.text
            assert client.post("/v1/tag-suggestions", json=data, headers=AUTH).json()["replayed"]
        assert len(calls) == 8
        with app.state.service.journal.connection() as db:
            row = db.execute("SELECT * FROM spending LIMIT 1").fetchone()
            assert row["reserved"] == 31128
            assert json.loads(row["policy"])["counted_input_tokens"] == 20000


@pytest.mark.parametrize("count", [None, True, "10", -1, 1048577])
def test_invalid_token_count_never_admits_generation(tmp_path, count):
    calls = []

    def response(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={"totalTokens": count})

    app = create_app(runtime(tmp_path), transport=httpx.MockTransport(response))
    with TestClient(app) as client:
        reply = client.post("/v1/tag-suggestions", json=gemini_request(), headers=AUTH)
        assert (
            reply.status_code == 503 and reply.json()["error"]["code"] == "token_count_unavailable"
        )
        assert len(calls) == 1 and calls[0].endswith(":countTokens")
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM spending").fetchone()[0] == 0


@pytest.mark.parametrize("failure", ["timeout", "http_error", "oversized", "malformed"])
def test_unavailable_token_count_does_not_generate_or_retry(tmp_path, failure):
    calls = []

    def response(req):
        calls.append(req.url.path)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic token count timeout", request=req)
        if failure == "http_error":
            return httpx.Response(429)
        return httpx.Response(200, content="x" * (8193 if failure == "oversized" else 1))

    app = create_app(runtime(tmp_path), transport=httpx.MockTransport(response))
    with TestClient(app) as client:
        reply = client.post("/v1/tag-suggestions", json=gemini_request(), headers=AUTH)
        assert reply.status_code == 503
        assert len(calls) == 1 and calls[0].endswith(":countTokens")


def test_usage_above_counted_reservation_requires_review(tmp_path):
    def response(req):
        body = answer(["mobility"])
        body["usageMetadata"].update(promptTokenCount=2000, totalTokenCount=2005)
        return httpx.Response(200, json=body)

    app = create_app(runtime(tmp_path), transport=gemini_transport(response))
    with TestClient(app) as client:
        assert (
            client.post("/v1/tag-suggestions", json=gemini_request(), headers=AUTH).status_code
            == 200
        )
        saved = client.get("/v1/attempts/request-1/spending", headers=AUTH).json()
        assert saved["review_required"] and saved["awaiting_reconciliation"]
        next_reply = client.post("/v1/tag-suggestions", json=gemini_request(2), headers=AUTH)
        assert next_reply.json()["error"]["code"] == "spending_review_required"


@pytest.mark.parametrize("status", [401, 403])
def test_provider_credentials_failure_is_not_a_retryable_server_failure(tmp_path, status):
    calls = []

    def response(req):
        calls.append(req)
        return httpx.Response(status, json={"error": {"message": "private provider detail"}})

    with TestClient(create_app(runtime(tmp_path), transport=gemini_transport(response))) as client:
        reply = client.post("/v1/tag-suggestions", headers=AUTH, json=gemini_request())
        assert reply.status_code == 503
        assert reply.json()["error"]["code"] == f"provider_http_{status}"
        assert reply.json()["status"] == "failed"
        assert "private provider detail" not in reply.text
        assert len(calls) == 1


def test_summary_new_job_for_same_source_keeps_original_spending_ceiling(tmp_path):
    from service.summary.config import SummaryConfig

    calls = []

    def response(req):
        calls.append(req)
        return httpx.Response(200, json=answer(content="invalid summary", usage=False))

    config = replace(runtime(tmp_path), paid_run_usd="0.04")
    app = create_app(config, transport=gemini_transport(response))
    data = summary_request()
    profile = SummaryConfig(ROOT, "gemini-daily-v1")
    data.update(model_id=profile.version, config_sha256=profile.sha256)
    with TestClient(app) as client:
        first = client.post("/v1/daily-summary-drafts", headers=AUTH, json=data)
        assert first.status_code == 502, first.text
        changed_job = {**data, "request_id": "new-profile-request", "job_id": "new-pinned-job"}
        refused = client.post("/v1/daily-summary-drafts", headers=AUTH, json=changed_job)
        assert refused.json()["error"]["code"] == "spending_limit", refused.text
        assert refused.json()["inference_admitted"] is False
        assert len(calls) == 1
        with app.state.service.journal.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM spending").fetchone()[0] == 1


@pytest.mark.parametrize("profile_id", ["hetzner-daily-v1", "gemini-daily-v1"])
@pytest.mark.parametrize("supplied_hash", [None, "0" * 64])
def test_current_summary_profiles_require_their_catalog_fingerprint(
    tmp_path, profile_id, supplied_hash
):
    data = summary_request()
    data.update(model_id=profile_id, config_sha256=supplied_hash)
    with TestClient(create_app(settings(tmp_path, summary_enabled=True))) as client:
        reply = client.post("/v1/daily-summary-drafts", headers=AUTH, json=data)
        assert reply.status_code == 422
        assert reply.json()["error"]["code"] == "unsupported_configuration"
        assert reply.json()["inference_admitted"] is False
        with client.app.state.service.journal.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


@pytest.mark.parametrize("provider", ["hetzner", "gemini"])
def test_unregistered_models_cannot_use_another_models_pricing(tmp_path, provider):
    from types import SimpleNamespace

    config = SimpleNamespace(provider=provider, model="unregistered-model")
    with pytest.raises(AdmissionError) as failure:
        spending.policy(runtime(tmp_path), config)
    assert failure.value.code == "pricing_review_required"


def test_second_registered_gemini_uses_its_own_model_endpoint_and_pricing(tmp_path, monkeypatch):
    from types import SimpleNamespace

    name = "synthetic-gemini-second"
    pricing = {
        **MODEL_CATALOG[ModelId.GEMINI_FLASH].pricing,
        "version": "synthetic-second-price",
        "model": name,
        "input_microusd_per_token": "1.00",
    }
    monkeypatch.setitem(MODEL_CATALOG, name, ModelDefinition(provider="gemini", pricing=pricing))
    config = SimpleNamespace(
        provider="gemini", model=name, endpoint=GeminiProvider.endpoint_for(name)
    )
    adapter = GeminiProvider(None, config, "synthetic-secret")
    approved = spending.policy(runtime(tmp_path), config, input_tokens=10, output_tokens=4096)
    assert adapter.model == name
    assert adapter.endpoint.endswith(f"/{name}:generateContent")
    assert approved["model"] == name and approved["version"] == "synthetic-second-price"
    assert approved["reservation"] == 16394
