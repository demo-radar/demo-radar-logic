"""Offline API contracts: prompt equivalence, replay, admission and uncertain failures."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from service.app import create_app
from service.config import InferenceConfig, Settings
from service.contracts import TagRequest
from service.persistence.journal import AdmissionError, Journal

ROOT = Path(__file__).resolve().parents[2]
AUTH = {"Authorization": "Bearer synthetic-test-token"}


def request(number=1, title="Für sichere Radwege"):
    """Use publishable invented text and stable IDs, never private fixture data."""
    return {
        "request_id": f"request-{number}",
        "job_id": "job-1",
        "source_version": "source-1",
        "event": {"id": f"synthetic-event-{number}", "title": title},
    }


def settings(tmp_path, **overrides):
    """A separate private journal per test; live transport is always simulated."""
    return Settings(
        token="synthetic-test-token",
        database=tmp_path / "state.sqlite",
        min_interval_seconds=0,
        **overrides,
    )


def completion(tags=None, content=None, **overrides):
    """Return a minimal synthetic OpenAI-compatible provider envelope."""
    return {
        "id": "fake-provider-id",
        "model": "Qwen/Qwen3.6-35B-A3B-FP8",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": content
                    if content is not None
                    else json.dumps({"tags": tags if tags is not None else ["mobility"]})
                },
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "prompt_tokens_details": {"cached_tokens": 20},
            "completion_tokens_details": {"reasoning_tokens": 3},
        },
        **overrides,
    }


def live_app(tmp_path, handler):
    """Make a live-mode app whose requests cannot reach an actual provider."""
    return create_app(
        settings(
            tmp_path,
            mode="live",
            provider_key="synthetic-provider-secret",
            free_tier_confirmed=True,
        ),
        transport=httpx.MockTransport(handler),
    )


def test_payload_matches_evaluated_notebook_and_excludes_ids():
    config = InferenceConfig(ROOT)
    original_path = ROOT / "notebooks/prompts/fresh-v4-confirmation-v1.json"
    original = json.loads(original_path.read_text())
    expected = copy.deepcopy(original["candidates"][0]["settings"])
    expected["messages"] = [
        {
            "role": "system",
            "content": original["wrapper"].replace("RUBRIC_VERSION", "4")
            + (ROOT / original["rubric"]["path"]).read_text(),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"title": "Öffentliche Versammlung — Frieden"}, ensure_ascii=False
            ),
        },
    ]
    assert config.payload("Öffentliche Versammlung — Frieden") == expected
    assert (
        config.data["experiment_sha256"] == hashlib.sha256(original_path.read_bytes()).hexdigest()
    )


def test_rubric_change_fails_startup(tmp_path):
    config_dir = tmp_path / "configs/inference"
    config_dir.mkdir(parents=True)
    config_dir.joinpath("catalog.json").write_bytes(
        (ROOT / "configs/inference/catalog.json").read_bytes()
    )
    config_dir.joinpath("qwen-v4-v1.json").write_bytes(
        (ROOT / "configs/inference/qwen-v4-v1.json").read_bytes()
    )
    rubric = tmp_path / "docs/rubrics/tagging-rubric-v4.md"
    rubric.parent.mkdir(parents=True)
    rubric.write_text("Different rules")
    with pytest.raises(ValueError, match="fingerprint"):
        InferenceConfig(tmp_path)


def test_demo_auth_validation_and_replay(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/health/live").status_code == 200
        assert client.post("/v1/tag-suggestions", json=request()).status_code == 401
        first = client.post("/v1/tag-suggestions", json=request(), headers=AUTH).json()
        assert first["tags"] == ["mobility"]
        assert first["mode"] == "demo" and first["new_provider_calls"] == 0
        assert first["statistics"]["returned_model"] == "synthetic-fixture-not-qwen"
        assert first["statistics"]["input_tokens"] is None
        assert first["requires_staff_review"] is True
        replay = client.post("/v1/tag-suggestions", json=request(), headers=AUTH).json()
        assert replay["replayed"] and replay["new_provider_calls"] == 0
        assert replay["statistics"] == first["statistics"]
        different = request(title="Changed title")
        assert client.post("/v1/tag-suggestions", json=different, headers=AUTH).status_code == 409
        assert client.get("/v1/openapi.json", headers=AUTH).status_code == 200
        real = request(2)
        real["event"]["id"] = "real-event"
        assert client.post("/v1/tag-suggestions", json=real, headers=AUTH).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"model_id": "another-model"},
        {"taxonomy_version": "v1"},
        {"input_variant": "F3"},
        {"decision_policy": {"threshold": 0.3}},
        {"search": True},
        {"event": {"id": "synthetic-1", "title": "  "}},
    ],
)
def test_unsupported_request_cannot_call_provider(tmp_path, change):
    calls = []
    with TestClient(live_app(tmp_path, lambda req: calls.append(req))) as client:
        response = client.post("/v1/tag-suggestions", json={**request(), **change}, headers=AUTH)
        assert response.status_code == 422
        assert not calls
        assert "Für sichere Radwege" not in response.text


def test_live_usage_and_restart_replay_make_only_one_call(tmp_path):
    calls = []

    def handler(req):
        calls.append(req)
        assert req.headers["authorization"] == "Bearer synthetic-provider-secret"
        return httpx.Response(200, json=completion())

    for index in range(2):
        with TestClient(live_app(tmp_path, handler)) as client:
            response = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
            assert response.status_code == 200
            result = response.json()
            assert result["replayed"] is bool(index)
            assert result["new_provider_calls"] == 1 - index
            assert result["statistics"]["input_tokens"] == 100
            assert result["statistics"]["total_tokens"] == 110
            assert result["statistics"]["reasoning_tokens"] == 3
    assert len(calls) == 1


def test_empty_tags_are_successful_abstention(tmp_path):
    with TestClient(
        live_app(tmp_path, lambda _: httpx.Response(200, json=completion(tags=[])))
    ) as client:
        result = client.post("/v1/tag-suggestions", json=request(), headers=AUTH).json()
        assert result["status"] == "abstained" and result["tags"] == []
        assert result["error"] is None


@pytest.mark.parametrize(
    "content",
    [
        '{"tags":["conflict"]}',
        '{"tags":["mobility","mobility"]}',
        '{"tags":["work","politics","religion"]}',
        '{"tags":[],"reason":"extra"}',
        "[]",
        '{"tags":"work"}',
    ],
)
def test_invalid_completion_is_not_an_abstention(tmp_path, content):
    with TestClient(
        live_app(tmp_path, lambda _: httpx.Response(200, json=completion(content=content)))
    ) as client:
        response = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        assert response.status_code == 502
        assert response.json()["tags"] is None
        assert response.json()["error"]["code"] == "invalid_provider_response"
        assert response.json()["statistics"]["input_tokens"] == 100


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.DecodingError])
def test_timeout_blocks_new_calls_and_survives_restart(tmp_path, failure):
    calls = []

    def handler(req):
        calls.append(req)
        raise failure("private provider text and secret", request=req)

    for index in range(2):
        with TestClient(live_app(tmp_path, handler)) as client:
            failed = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
            assert failed.status_code == 504
            assert failed.json()["status"] == "unknown"
            assert "private provider" not in failed.text
            assert failed.json()["statistics"]["input_tokens"] is None
            assert (
                client.post("/v1/tag-suggestions", json=request(2), headers=AUTH).status_code == 409
            )
            assert client.get("/health/ready", headers=AUTH).status_code == 503
    assert len(calls) == 1


def test_rate_limit_wait_persists_without_retry_or_error_body_leak(tmp_path):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(
            429, headers={"Retry-After": "120"}, text="secret token and private title"
        )

    with TestClient(live_app(tmp_path, handler)) as client:
        response = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        assert response.status_code == 429 and response.headers["retry-after"] == "120"
        assert "secret token" not in response.text
        assert client.post("/v1/tag-suggestions", json=request(2), headers=AUTH).status_code == 429
    assert len(calls) == 1


def test_private_journal_attempt_and_batch_caps(tmp_path):
    journal = Journal(tmp_path / "state.sqlite")
    assert journal.path.stat().st_mode & 0o777 == 0o600
    r = TagRequest(**request())
    for n in range(3):
        r.request_id = f"retry-{n}"
        assert journal.begin(r, f"identity-{n}", "event-key", 0) is None
        journal.finish(r.request_id, {"error": "failed"}, 502, "failed")
    r.request_id = "retry-4"
    with pytest.raises(AdmissionError) as exc:
        journal.begin(r, "identity-4", "event-key", 0)
    assert exc.value.code == "event_attempt_limit"
    other = Journal(tmp_path / "batch.sqlite")
    from service.tasks.limits import MAX_JOB_ATTEMPTS

    for n in range(MAX_JOB_ATTEMPTS):
        r = TagRequest(**request(n))
        other.begin(r, str(n), str(n), 0)
        other.finish(r.request_id, {"tags": []}, 200, "ok")
    with pytest.raises(AdmissionError) as exc:
        other.begin(TagRequest(**request(41)), "41", "41", 0)
    assert exc.value.code == "batch_limit"


def test_two_instances_drain_active_call_before_accepting_more(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(req):
            entered.set()
            await release.wait()
            return httpx.Response(200, json=completion())

        apps = [live_app(tmp_path, handler), live_app(tmp_path, handler)]
        async with (
            apps[0].router.lifespan_context(apps[0]),
            apps[1].router.lifespan_context(apps[1]),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=apps[0]), base_url="http://test", headers=AUTH
            ) as first,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=apps[1]), base_url="http://test", headers=AUTH
            ) as second,
        ):
            task = asyncio.create_task(first.post("/v1/tag-suggestions", json=request()))
            await asyncio.wait_for(entered.wait(), 2)
            assert (await second.post("/v1/tag-suggestions", json=request(2))).status_code == 409
            assert (await second.post("/v1/maintenance")).status_code == 202
            assert (await second.delete("/v1/maintenance")).status_code == 409
            assert (await first.post("/v1/tag-suggestions", json=request(3))).status_code == 503
            release.set()
            assert (await task).status_code == 200
            assert (await second.post("/v1/maintenance")).json()["drained"]
            assert (await second.get("/health/ready")).status_code == 503
            assert (await second.delete("/v1/maintenance")).status_code == 200
            assert (await second.get("/health/ready")).status_code == 200

    asyncio.run(scenario())


def test_disconnect_does_not_abandon_admitted_call(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(req):
            entered.set()
            await release.wait()
            return httpx.Response(200, json=completion())

        app = live_app(tmp_path, handler)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", headers=AUTH
            ) as client,
        ):
            task = asyncio.create_task(client.post("/v1/tag-suggestions", json=request()))
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert app.state.service.active
            release.set()
            await asyncio.gather(*app.state.service.active)
            replay = (await client.post("/v1/tag-suggestions", json=request())).json()
            assert replay["replayed"] and replay["tags"] == ["mobility"]

    asyncio.run(scenario())


def test_elapsed_deadline_marks_uncertain_attempt(tmp_path):
    async def handler(req):
        await asyncio.sleep(2)
        return httpx.Response(200, json=completion())

    config = settings(
        tmp_path, mode="live", provider_key="fake", free_tier_confirmed=True, timeout_seconds=1
    )
    with TestClient(create_app(config, transport=httpx.MockTransport(handler))) as client:
        result = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        assert result.status_code == 504
        assert result.json()["statistics"]["duration_seconds"] < 1.5
        evidence = client.get("/v1/attempts/request-1", headers=AUTH).json()
        assert evidence["status"] == "unknown" and evidence["new_provider_calls"] == 0


def test_failed_persistence_retains_pre_dispatch_marker(tmp_path, monkeypatch):
    import sqlite3

    with TestClient(live_app(tmp_path, lambda _: httpx.Response(200, json=completion()))) as client:

        def broken_save(*args):
            raise sqlite3.OperationalError("private SQL detail")

        monkeypatch.setattr(client.app.state.service.journal, "finish", broken_save)
        response = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        assert response.status_code == 503
        assert "private SQL" not in response.text
        marker = client.get("/v1/attempts/request-1", headers=AUTH)
        assert marker.status_code == 202 and marker.json()["started_at"]
        assert client.post("/v1/tag-suggestions", json=request(2), headers=AUTH).status_code == 409


def test_openapi_describes_selected_result_contract(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        schema = client.get("/v1/openapi.json", headers=AUTH).json()
        result_schema = schema["components"]["schemas"]["TagResponse"]
        assert "tags" in result_schema["properties"]
        assert "statistics" in result_schema["required"]
        assert "/v1/jobs" not in schema["paths"]


@pytest.mark.parametrize("metadata", [{"id": 123}, {"usage": []}])
def test_invalid_provider_metadata_returns_replayable_failure(tmp_path, metadata):
    with TestClient(
        live_app(tmp_path, lambda _: httpx.Response(200, json=completion(**metadata)))
    ) as client:
        response = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "invalid_provider_response"
        assert client.post("/v1/tag-suggestions", json=request(), headers=AUTH).json()["replayed"]
        assert client.get("/health/ready", headers=AUTH).status_code == 200


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps(completion(usage={"total_tokens": float("nan")})),
        json.dumps(completion(id="bad\ud800identifier")),
        '{"choices": [], "choices": []}',
    ],
)
def test_nonstandard_provider_json_never_commits_success(tmp_path, raw):
    with TestClient(
        live_app(tmp_path, lambda _: httpx.Response(200, content=raw.encode()))
    ) as client:
        response = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        assert response.status_code == 502
        assert response.json()["status"] == "unknown"
        assert response.json()["error"]["code"] == "invalid_provider_json"
        assert client.get("/health/ready", headers=AUTH).status_code == 503


def test_failed_completion_preserves_provider_identity(tmp_path):
    with TestClient(
        live_app(tmp_path, lambda _: httpx.Response(200, json=completion(content="not JSON")))
    ) as client:
        result = client.post("/v1/tag-suggestions", json=request(), headers=AUTH).json()
        assert result["statistics"]["provider_request_id"] == "fake-provider-id"
        assert result["statistics"]["returned_model"] == completion()["model"]
        assert result["statistics"]["total_tokens"] == 110


def test_duplicate_tag_fields_are_not_silently_accepted(tmp_path):
    with TestClient(
        live_app(
            tmp_path,
            lambda _: httpx.Response(
                200, json=completion(content='{"tags":["work"],"tags":["mobility"]}')
            ),
        )
    ) as client:
        assert client.post("/v1/tag-suggestions", json=request(), headers=AUTH).status_code == 502


@pytest.mark.parametrize("header", ["1.5", "172800", "Wed, 01 Jan 2031 00:00:00 GMT"])
def test_retry_after_formats_survive_replay_and_restart(tmp_path, header):
    import math
    import time
    from email.utils import parsedate_to_datetime

    expected = (
        parsedate_to_datetime(header).timestamp() - time.time() if "," in header else float(header)
    )
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(429, headers={"Retry-After": header})

    for _ in range(2):
        with TestClient(live_app(tmp_path, handler)) as client:
            result = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
            assert result.status_code == 429
            assert int(result.headers["retry-after"]) >= math.ceil(expected) - 2
            assert (
                client.post("/v1/tag-suggestions", json=request(2), headers=AUTH).status_code == 429
            )
    assert len(calls) == 1


def test_exceptional_shutdown_waits_for_disconnected_work(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(req):
            entered.set()
            await release.wait()
            return httpx.Response(200, json=completion())

        app = live_app(tmp_path, handler)
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers=AUTH
        ) as client:
            caller = asyncio.create_task(client.post("/v1/tag-suggestions", json=request()))
            await asyncio.wait_for(entered.wait(), 2)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
            shutdown = asyncio.create_task(
                lifespan.__aexit__(RuntimeError, RuntimeError("stop"), None)
            )
            await asyncio.sleep(0)
            assert not shutdown.done()
            release.set()
            await shutdown
            saved = (await client.get("/v1/attempts/request-1")).json()
            assert saved["status"] == "suggested"
            assert not app.state.service.active

    asyncio.run(scenario())


def test_invalid_unicode_input_is_rejected_before_dispatch(tmp_path):
    calls = []
    with TestClient(live_app(tmp_path, lambda req: calls.append(req))) as client:
        response = client.post(
            "/v1/tag-suggestions",
            content=json.dumps(request(title="bad\ud800title")),
            headers={**AUTH, "Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert calls == []


def test_hard_quota_is_not_reported_as_retryable_and_retains_error_usage(tmp_path):
    body = {
        "error": {"code": "insufficient_quota", "message": "private provider message"},
        "id": "failed-provider-id",
        "usage": {"total_tokens": 7},
    }
    with TestClient(live_app(tmp_path, lambda _: httpx.Response(429, json=body))) as client:
        response = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        result = response.json()
        assert response.status_code == 429
        assert result["error"]["code"] == "provider_quota_exhausted"
        assert not result["error"]["retryable"]
        assert result["statistics"]["provider_request_id"] == "failed-provider-id"
        assert result["statistics"]["total_tokens"] == 7
        assert "private provider message" not in response.text


@pytest.mark.parametrize(
    "field", ["version", "taxonomy_version", "maximum_predicted_tags", "model"]
)
def test_inconsistent_config_is_rejected_at_startup(tmp_path, field):
    config_dir = tmp_path / "configs/inference"
    config_dir.mkdir(parents=True)
    config_dir.joinpath("catalog.json").write_bytes(
        (ROOT / "configs/inference/catalog.json").read_bytes()
    )
    data = json.loads((ROOT / "configs/inference/qwen-v4-v1.json").read_text())
    if field == "model":
        data["candidate"]["settings"]["model"] = "unapproved-model"
    else:
        data[field] = "unexpected"
    (config_dir / "qwen-v4-v1.json").write_text(json.dumps(data))
    rubric = tmp_path / data["rubric"]["path"]
    rubric.parent.mkdir(parents=True)
    rubric.write_bytes((ROOT / data["rubric"]["path"]).read_bytes())
    with pytest.raises(ValueError, match="contract"):
        InferenceConfig(tmp_path)


def test_errors_have_readable_messages_and_http_status(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        for path, headers, body, expected in [
            ("/v1/tag-suggestions", {}, request(), 401),
            ("/v1/tag-suggestions", AUTH, {**request(), "max_attempts": 8}, 422),
            ("/does-not-exist", AUTH, None, 404),
        ]:
            response = client.post(path, json=body, headers=headers)
            error = response.json()["error"]
            assert response.status_code == error["http_status"] == expected
            assert error["code"] and len(error["message"]) > 15
            assert "synthetic-test-token" not in response.text
    with TestClient(
        live_app(tmp_path, lambda _: httpx.Response(429, headers={"Retry-After": "10"}))
    ) as client:
        response = client.post("/v1/tag-suggestions", json=request(), headers=AUTH)
        assert response.json()["error"]["http_status"] == 429
        assert "provider" in response.json()["error"]["message"].lower()


def test_operator_attempt_override_is_bounded_and_durable(tmp_path):
    journal = Journal(tmp_path / "override.sqlite", max_attempts=5)
    event = TagRequest(**request())
    for number in range(5):
        event.request_id = f"attempt-{number}"
        journal.begin(event, str(number), "same-event", 0)
        journal.finish(event.request_id, {"tags": None}, 502, "failed")
    restarted = Journal(journal.path, max_attempts=5)
    event.request_id = "sixth-attempt"
    with pytest.raises(AdmissionError) as exc:
        restarted.begin(event, "sixth", "same-event", 0)
    assert exc.value.code == "event_attempt_limit"
    for invalid in [0, 11, True]:
        with pytest.raises(ValueError):
            settings(tmp_path, max_attempts_per_event=invalid)


def test_legacy_journal_upgrade_preserves_results_and_cooldown(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE control(id INTEGER PRIMARY KEY, maintenance INTEGER, next_allowed REAL)"
        )
        db.execute("INSERT INTO control VALUES(1, 1, 2000000000)")
        db.execute("""CREATE TABLE attempts(request_id TEXT PRIMARY KEY, identity TEXT,
            event_key TEXT, event_id TEXT, job_id TEXT, status TEXT, result TEXT,
            http_status INTEGER, started_at TEXT)""")
        db.execute(
            "INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?)",
            (
                "old-id",
                "hash",
                "event-hash",
                "event",
                "job",
                "ok",
                '{"tags":["work"],"statistics":{"total_tokens":9}}',
                200,
                "original-time",
            ),
        )
    journal = Journal(path)
    assert journal.maintenance() == {"maintenance": True, "unresolved_attempts": 0, "drained": True}
    saved, status = journal.get_attempt("old-id")
    assert status == 200 and saved["tags"] == ["work"]
    assert saved["statistics"]["total_tokens"] == 9
    assert int(journal.retry_headers()["Retry-After"]) > 0
    with journal.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert (
            db.execute("SELECT result, started_at FROM attempts").fetchone()[1] == "original-time"
        )
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE attempts SET status='invalid' WHERE request_id='old-id'")
    assert Journal(path).get_attempt("old-id")[0]["tags"] == ["work"]


def test_schema_guards_and_completed_results_cannot_be_overwritten(tmp_path):
    import sqlite3

    journal = Journal(tmp_path / "guard.sqlite")
    journal.begin(TagRequest(**request()), "identity", "event-key", 0)
    with journal.connection() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO attempts VALUES(?,?,?,?,?,'started',NULL,NULL,?)",
            ("second", "hash", "second-event", "e2", "job", "now"),
        )
    journal.finish("request-1", {"tags": ["mobility"]}, 200, "ok")
    with pytest.raises(AdmissionError):
        journal.finish("request-1", {"tags": ["work"]}, 200, "ok")
    assert journal.get_attempt("request-1")[0]["tags"] == ["mobility"]


def test_provider_factory_is_explicit_and_secrets_are_not_repr(tmp_path):
    from service.providers.factory import create_provider
    from service.providers.hetzner import HetznerProvider
    from service.providers.synthetic import SyntheticProvider

    config = InferenceConfig(ROOT)
    demo_settings = settings(tmp_path)
    assert isinstance(create_provider(demo_settings, config, None), SyntheticProvider)
    live_settings = settings(
        tmp_path, mode="live", provider_key="private-value", free_tier_confirmed=True
    )
    assert isinstance(create_provider(live_settings, config, None), HetznerProvider)
    assert "private-value" not in repr(live_settings)
    assert "synthetic-test-token" not in repr(live_settings)
    config.provider = "gemini"
    with pytest.raises(ValueError, match="Unsupported Gemini"):
        create_provider(live_settings, config, None)


def test_higher_event_allowance_does_not_raise_total_batch_limit(tmp_path):
    journal = Journal(tmp_path / "batch-override.sqlite", max_attempts=5)
    from service.tasks.limits import MAX_JOB_ATTEMPTS

    for number in range(MAX_JOB_ATTEMPTS):
        event = TagRequest(**request(number // 4))
        event.request_id = f"attempt-{number}"
        journal.begin(event, str(number), str(number // 4), 0)
        journal.finish(event.request_id, {"tags": None}, 502, "failed")
    event = TagRequest(**request(31))
    with pytest.raises(AdmissionError) as exc:
        journal.begin(event, "over-limit", "31", 0)
    assert exc.value.code == "batch_limit"


def test_hetzner_adapter_rejects_unapproved_destination_before_using_credentials():
    from service.providers.hetzner import HetznerProvider

    config = InferenceConfig(ROOT)
    config.endpoint = "https://unapproved.invalid/chat/completions"
    with pytest.raises(ValueError, match="Unsupported Hetzner model or endpoint"):
        HetznerProvider(None, config, "private-test-value")


def test_admission_errors_explicitly_confirm_no_inference(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        unauthorized = client.post("/v1/tag-suggestions", json=request())
        assert unauthorized.status_code == 401
        assert unauthorized.json()["inference_admitted"] is False
        invalid = client.post("/v1/tag-suggestions", json={}, headers=AUTH)
        assert invalid.status_code == 422
        assert invalid.json()["inference_admitted"] is False


def test_save_conflict_never_claims_no_inference():
    from service.api.exception_handlers import rejected

    reply = asyncio.run(rejected(None, AdmissionError("attempt_already_finalized")))
    assert "inference_admitted" not in json.loads(reply.body)


@pytest.mark.parametrize("limit", [0, 31, 120, True])
def test_journal_rejects_job_allowances_outside_the_server_ceiling(tmp_path, limit):
    journal = Journal(tmp_path / "invalid-limit.sqlite")
    with pytest.raises(ValueError, match="Job attempts"):
        journal.begin(TagRequest(**request()), "identity", "event-key", 0, max_job_attempts=limit)
    with journal.connection() as db:
        assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
