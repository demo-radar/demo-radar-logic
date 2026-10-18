"""Offline recovery preserves evidence and prevents unsafe or duplicate work."""

from datetime import UTC, datetime, timedelta

import pytest

from service.contracts import TagRequest
from service.persistence.journal import AdmissionError, Journal
from service.persistence.locking import server_lock


def request(number=1, event="synthetic-one"):
    return TagRequest(
        request_id=f"request-{number}",
        job_id="job-1",
        source_version="source-1",
        event={"id": event, "title": "Invented title"},
    )


def unknown(journal, *, age=3600):
    item = request()
    journal.begin(item, "identity", "input-one", 0)
    body = {
        "status": "unknown",
        "statistics": {
            "finished_at": (datetime.now(UTC) - timedelta(seconds=age)).isoformat(),
            "total_tokens": None,
        },
    }
    journal.finish(item.request_id, body, 504, "unknown")
    return body


def test_recovery_retains_original_response_and_blocks_the_same_input(tmp_path):
    journal = Journal(tmp_path / "state.sqlite")
    body = unknown(journal)
    journal.maintenance(True)
    result = journal.close_unknown(
        "request-1",
        operator="local-admin",
        reason="Investigated old timeout; abandon its unknown result",
    )
    assert result["request_id"] == "request-1"
    saved, code = journal.get_attempt("request-1")
    assert code == 200 and saved["status"] == body["status"] == "unknown"
    assert saved["statistics"] == body["statistics"]
    assert saved["resolution"] == {
        "action": "abandoned_unknown",
        "resolved_at": result["resolved_at"],
    }
    with journal.connection() as db:
        import json

        original = json.loads(
            db.execute("SELECT result FROM attempts WHERE request_id=?", ("request-1",)).fetchone()[
                0
            ]
        )
    assert original == body
    assert journal.attempt_count("input-one") == 1
    assert journal.maintenance(False)["drained"]
    with pytest.raises(AdmissionError, match="event_outcome_closed_unknown"):
        journal.begin(request(2), "new-id", "input-one", 0)
    assert journal.begin(request(3, "synthetic-three"), "other-id", "other-input", 0) is None
    assert journal.maintenance()["unresolved_attempts"] == 1


def test_recovery_requires_maintenance_and_rejects_recent_or_started_work(tmp_path):
    journal = Journal(tmp_path / "state.sqlite")
    unknown(journal, age=60)
    with pytest.raises(AdmissionError, match="maintenance_required"):
        journal.close_unknown("request-1", operator="admin", reason="Investigated timeout")
    journal.maintenance(True)
    with pytest.raises(AdmissionError, match="recovery_wait_required"):
        journal.close_unknown("request-1", operator="admin", reason="Investigated timeout")
    with pytest.raises(AdmissionError, match="attempt_not_finalized_unknown"):
        journal.close_unknown("missing", operator="admin", reason="Investigated timeout")
    other = Journal(tmp_path / "started.sqlite")
    other.begin(request(), "id", "event", 0)
    other.maintenance(True)
    with pytest.raises(AdmissionError, match="attempt_not_finalized_unknown"):
        other.close_unknown("request-1", operator="admin", reason="Investigated timeout")


def test_offline_recovery_cannot_run_while_any_server_uses_the_journal(tmp_path):
    database = tmp_path / "state.sqlite"
    with (
        server_lock(database),
        server_lock(database),
        pytest.raises(RuntimeError, match="Stop DemoLogic"),
        server_lock(database, exclusive=True),
    ):
        pytest.fail("Recovery acquired a live server's lock")
    with server_lock(database, exclusive=True), pytest.raises(RuntimeError), server_lock(database):
        pytest.fail("Server started during recovery")


def test_repeated_recovery_is_idempotent_and_keeps_the_first_explanation(tmp_path):
    journal = Journal(tmp_path / "state.sqlite")
    unknown(journal)
    journal.maintenance(True)
    kwargs = {"operator": "admin", "reason": "Investigated timeout; abandon result"}
    first = journal.close_unknown("request-1", **kwargs)
    assert journal.close_unknown("request-1", **kwargs) == first
    with pytest.raises(AdmissionError, match="resolution_conflict"):
        journal.close_unknown("request-1", operator="different-admin", reason=kwargs["reason"])


def test_online_recovery_is_authenticated_audited_and_survives_restart(tmp_path):
    from fastapi.testclient import TestClient

    from service.app import create_app

    from .test_api import AUTH, settings

    runtime = settings(tmp_path)
    journal = Journal(runtime.database)
    body = unknown(journal)
    action = {
        "operator": "admin",
        "reason": "Investigated timeout; abandon unknown answer",
        "accept_unknown_outcome": True,
    }
    path = "/v1/attempts/request-1/close"
    with TestClient(create_app(runtime)) as client:
        assert client.post(path, json=action).status_code == 401
        for value in (False, 1, "true", None):
            assert (
                client.post(
                    path, headers=AUTH, json={**action, "accept_unknown_outcome": value}
                ).status_code
                == 422
            )
        assert (
            client.post(path, headers=AUTH, json={**action, "reason": "         x"}).status_code
            == 422
        )
        state = client.get("/v1/recovery", headers=AUTH).json()
        assert state["items"][0]["can_close"] is True
        assert client.post(path, headers=AUTH, json=action).status_code == 200
        assert client.post(path, headers=AUTH, json=action).status_code == 200
        assert client.get("/health/ready", headers=AUTH).json()["ready"]
    with TestClient(create_app(runtime)) as restarted:
        saved = restarted.get("/v1/attempts/request-1", headers=AUTH).json()
        assert saved["status"] == body["status"] and saved["statistics"] == body["statistics"]
        assert saved["resolution"]["action"] == "abandoned_unknown"
        assert restarted.get("/v1/recovery", headers=AUTH).json()["items"] == []
    with journal.connection() as db:
        audit = dict(db.execute("SELECT * FROM attempt_resolutions").fetchone())
    assert audit["operator"] == "admin" and audit["reason"] == action["reason"]


def test_online_recovery_excludes_all_active_processes_and_started_markers(tmp_path):
    from service.inference.recovery import RecoveryService
    from service.persistence.locking import activity_lock

    journal = Journal(tmp_path / "state.sqlite")
    unknown(journal)
    recovery = RecoveryService(journal)
    with activity_lock(journal.path), pytest.raises(AdmissionError, match="recovery_inflight"):
        recovery.close("request-1", operator="admin", reason="Investigated timeout")
    with (
        activity_lock(journal.path, exclusive=True),
        pytest.raises(AdmissionError, match="recovery_inflight"),
        activity_lock(journal.path),
    ):
        pytest.fail("Inference entered during recovery")
    other = Journal(tmp_path / "crashed.sqlite")
    other.begin(request(), "id", "key", 0)
    with pytest.raises(AdmissionError, match="attempt_not_finalized_unknown"):
        RecoveryService(other).close(
            "request-1", operator="admin", reason="Investigated worker crash"
        )
    assert other.recovery_status()["items"][0]["can_close"] is False
    assert not other.maintenance()["drained"]


def test_disconnect_keeps_activity_lock_until_the_saved_answer_finishes(tmp_path):
    import asyncio
    from pathlib import Path

    from service.config import InferenceConfig, Settings
    from service.inference.coordinator import InferenceService
    from service.persistence.locking import activity_lock

    async def run():
        journal = Journal(tmp_path / "state.sqlite")
        runtime = Settings(token="test-token", database=journal.path, min_interval_seconds=0)
        config = InferenceConfig(Path(__file__).resolve().parents[2])
        service = InferenceService(runtime, config, journal, None)
        entered, finish = asyncio.Event(), asyncio.Event()

        async def execute():
            entered.set()
            await finish.wait()
            journal.finish("request-1", {"status": "failed"}, 502, "failed")
            return {"status": "failed"}, 502

        caller = asyncio.create_task(service._admit(request(), "id", "key", execute))
        await asyncio.wait_for(entered.wait(), timeout=2)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        with (
            pytest.raises(AdmissionError, match="recovery_inflight"),
            activity_lock(journal.path, exclusive=True),
        ):
            pytest.fail("Recovery overlapped disconnected inference")
        finish.set()
        await service.close()
        with activity_lock(journal.path, exclusive=True):
            assert journal.maintenance()["drained"]

    asyncio.run(run())


def test_crashed_process_releases_lock_but_keeps_unfinished_marker(tmp_path):
    import subprocess
    import sys

    from service.inference.recovery import RecoveryService
    from service.persistence.locking import activity_lock

    journal = Journal(tmp_path / "state.sqlite")
    journal.begin(request(), "id", "key", 0)
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys; from service.persistence.locking import activity_lock; "
                "lock=activity_lock(sys.argv[1]); lock.__enter__(); print('ready', flush=True); sys.stdin.read()"
            ),
            str(journal.path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "ready"
        with (
            pytest.raises(AdmissionError, match="recovery_inflight"),
            activity_lock(journal.path, exclusive=True),
        ):
            pytest.fail("Recovery entered while another process was active")
        child.kill()
        child.wait(timeout=5)
        with activity_lock(journal.path, exclusive=True):
            assert journal.maintenance()["unresolved_attempts"] == 1
        with pytest.raises(AdmissionError, match="attempt_not_finalized_unknown"):
            RecoveryService(journal).close(
                "request-1", operator="admin", reason="Investigated worker crash"
            )
        assert journal.recovery_status()["items"][0]["can_close"] is False
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()
