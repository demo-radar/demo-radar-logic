"""Read-only operational evidence, including replay, uncertainty and late charges."""

import json

from fastapi.testclient import TestClient

from service.app import create_app
from service.observability.attempts import AttemptMeasurements
from service.persistence.journal import Journal
from tests.service.test_api import AUTH, completion, live_app, request, settings


def test_monitoring_auth_and_reads_make_no_provider_calls(tmp_path):
    calls = []
    import httpx

    def provider(incoming):
        calls.append(incoming)
        return httpx.Response(200, json=completion())

    with TestClient(live_app(tmp_path, provider)) as client:
        assert client.get("/v1/monitoring/attempts").status_code == 401
        assert client.get("/v1/monitoring/attempts?after=-1", headers=AUTH).status_code == 422
        original = client.post("/v1/tag-suggestions", headers=AUTH, json=request()).json()
        client.post("/v1/tag-suggestions", headers=AUTH, json=request())
        first = client.get("/v1/monitoring/attempts", headers=AUTH).json()
        assert len(first["attempts"]) == len(calls) == 1
        assert first == client.get("/v1/monitoring/attempts", headers=AUTH).json()
        measured = first["attempts"][0]
        assert measured["request_id"] == original["request_id"]
        assert measured["dispatch"] == "confirmed"
        assert measured["input_tokens"] == 100
        assert measured["cached_input_tokens"] == 20
        assert measured["reasoning_tokens"] == 3
        assert measured["provider_seconds"] >= 0
        assert measured["queue_seconds"] >= 0
        assert measured["cost_state"] == "unavailable"
        for private in ("Für sichere", "synthetic-provider-secret", "usage_raw", "event_id"):
            assert private not in json.dumps(first)
        assert (
            client.get(
                f"/v1/monitoring/attempts?after={first['next_cursor']}", headers=AUTH
            ).json()["attempts"]
            == []
        )


def test_unknown_and_malformed_responses_keep_distinct_evidence(tmp_path):
    import httpx

    def provider(incoming):
        return httpx.Response(200, json=completion(content="not JSON"))

    with TestClient(live_app(tmp_path, provider)) as client:
        assert client.post("/v1/tag-suggestions", headers=AUTH, json=request()).status_code == 502
        row = client.get("/v1/monitoring/attempts", headers=AUTH).json()["attempts"][0]
        assert row["outcome"] == "failed" and row["dispatch"] == "confirmed"
        assert row["total_tokens"] == 110

    def timeout(incoming):
        raise httpx.ReadTimeout("private network details")

    with TestClient(live_app(tmp_path / "unknown", timeout)) as client:
        client.post("/v1/tag-suggestions", headers=AUTH, json=request())
        row = client.get("/v1/monitoring/attempts", headers=AUTH).json()["attempts"][0]
        assert row["outcome"] == "unknown" and row["dispatch"] == "possible"
        assert row["total_tokens"] is None


def test_late_reconciliation_is_read_from_ledger_not_original_reply(tmp_path):
    journal = Journal(tmp_path / "ledger.sqlite")
    from service.contracts import TagRequest

    payload = TagRequest.model_validate(request())
    journal.begin(
        payload,
        "identity",
        "event",
        0,
        execution={"mode": "live", "task": "tagging"},
        allowance_key="allowance",
    )
    journal.mark_execution(payload.request_id, started_at="2026-10-28T10:00:01+00:00")
    journal.finish(payload.request_id, {"status": "failed", "statistics": None}, 502, "failed")
    with journal.connection() as db:
        db.execute(
            "INSERT INTO spending VALUES(?,?,?,?,?,?,?,?)",
            (
                payload.request_id,
                "job-1",
                "private-account",
                "2026-10-28",
                1000,
                None,
                json.dumps({"version": "test-price", "currency": "USD"}),
                0,
            ),
        )
    first = AttemptMeasurements(journal).page()
    before = first["attempts"][0]
    assert before["cost_state"] == "awaiting_reconciliation"
    assert before["charged_microusd"] is None
    with journal.connection() as db:
        db.execute("UPDATE spending SET charged=123")
        db.execute(
            "INSERT INTO spending_audit VALUES(1,?,?,?,?,?,?)",
            (payload.request_id, "private-operator", "private-reason", None, 123, "2026-10-28"),
        )
    changes = AttemptMeasurements(journal).page(first["next_cursor"])
    assert len(changes["attempts"]) == 1
    assert changes["next_cursor"] > first["next_cursor"]
    after = changes["attempts"][0]
    assert after["cost_state"] == "reconciled" and after["charged_microusd"] == 123
    assert "private-" not in json.dumps(after)


def test_pages_are_bounded_and_synthetic_work_is_not_a_live_dispatch(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/v1/tag-suggestions", headers=AUTH, json=request())
        row = client.get("/v1/monitoring/attempts", headers=AUTH).json()["attempts"][0]
        assert row["mode"] == "synthetic" and row["dispatch"] == "none"
    journal = Journal(tmp_path / "state.sqlite")
    with journal.connection() as db:
        for index in range(1, 105):
            db.execute(
                "INSERT INTO attempts VALUES(?,?,?,?,?,'failed','{}',502,?)",
                (f"old-{index}", "identity", "event", "event", "job", "2026-10-28T10:00:00+00:00"),
            )
    first = AttemptMeasurements(journal).page()
    second = AttemptMeasurements(journal).page(first["next_cursor"])
    assert len(first["attempts"]) == 100 and first["complete"] is False
    assert len(second["attempts"]) == 5 and second["complete"] is True


def test_audited_closure_advances_measurement_cursor_without_losing_unknown_usage(tmp_path):
    from datetime import UTC, datetime

    from service.contracts import TagRequest

    journal = Journal(tmp_path / "closed.sqlite")
    payload = TagRequest.model_validate(request())
    journal.begin(
        payload,
        "identity",
        "event",
        0,
        execution={"mode": "live", "task": "tagging"},
        allowance_key="allowance",
    )
    journal.mark_execution(payload.request_id, started_at="2026-10-28T10:00:00+00:00")
    journal.finish(payload.request_id, {"status": "unknown"}, 504, "unknown")
    before = AttemptMeasurements(journal).page()
    with journal.connection() as db:
        db.execute(
            "INSERT INTO attempt_resolutions VALUES(?,?,?,?)",
            (
                payload.request_id,
                "private operator",
                "private reason",
                datetime.now(UTC).isoformat(),
            ),
        )
    after = AttemptMeasurements(journal).page(before["next_cursor"])
    assert len(after["attempts"]) == 1
    row = after["attempts"][0]
    assert row["unknown_closed"] is True and row["outcome"] == "unknown"
    assert row["total_tokens"] is None
    assert "private" not in json.dumps(row)
