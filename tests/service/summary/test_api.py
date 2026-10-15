"""Offline DR-33 checks; synthetic facts and mocked providers only."""

import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from service.app import create_app
from service.config import Settings
from service.contracts import TagRequest
from service.inference.results import fingerprint
from service.persistence.journal import AdmissionError
from service.providers.base import ProviderFailure
from service.summary.config import SummaryConfig
from service.summary.contracts import SummaryRequest
from service.summary.provider import HetznerSummaryProvider

AUTH = {"Authorization": "Bearer test-token"}


def request():
    snapshot = {
        "schema_version": 1,
        "date": "2026-10-10",
        "timezone": "Europe/Berlin",
        "language": "de",
        "visibility_rule": "active-public-feed-v1",
        "coverage": "registered-feed-only",
        "exclusions": [],
        "events": [
            {
                "id": "synthetic-one",
                "title": "Für sichere Radwege",
                "start": None,
                "end": None,
                "location": None,
                "route": None,
                "tags": [],
                "cancelled": None,
                "uncertainty": ["Location unknown"],
            }
        ],
    }
    return {
        "request_id": "daily-one",
        "job_id": "daily-job",
        "model_id": "daily-summary-v1",
        "config_sha256": SummaryConfig(Path(__file__).resolve().parents[3]).sha256,
        "snapshot_sha256": fingerprint(snapshot),
        "snapshot": snapshot,
    }


def app(tmp_path, handler=None, **changes):
    config = Settings(
        token="test-token",
        database=tmp_path / "shared.sqlite",
        min_interval_seconds=0,
        summary_enabled=True,
        **changes,
    )
    return create_app(config, transport=httpx.MockTransport(handler) if handler else None)


def completion(content, *, positional=False):
    content = copy.deepcopy(content)
    content.setdefault(
        "topics",
        [
            {
                "label": "Test",
                "event_ids": list(
                    dict.fromkeys(
                        identifier
                        for claim in content.get("overview", [])
                        for identifier in claim["event_ids"]
                    )
                ),
            }
        ],
    )
    for topic in content["topics"]:
        topic.setdefault("text", "Ein synthetisches Tagesthema.")
        topic.setdefault("include_in_briefing", True)
    aliases = {"synthetic-one": "d001", "synthetic-two": "d002"}
    for claim in [
        *content.get("overview", []),
        *content["topics"],
        *([content["highlight"]] if content.get("highlight") else []),
    ]:
        claim["event_ids"] = [
            aliases.get(identifier, identifier) for identifier in claim["event_ids"]
        ]
    if positional:
        memberships = {}
        for number, topic in enumerate(content["topics"], start=1):
            for identifier in topic.pop("event_ids"):
                memberships.setdefault(identifier, []).append(number)
        content["assignments"] = [memberships.get("d001", [])]
        if "d002" in memberships:
            content["assignments"].append(memberships["d002"])
    content.setdefault("highlight", None)
    if isinstance(content["highlight"], dict):
        content["highlight"].setdefault("title", "Synthetic demonstration")
    if not content.get("limitations"):
        content["limitations"] = ["Registered feed only."]
    return {
        "model": "Qwen/Qwen3.6-35B-A3B-FP8",
        "id": "fake",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
    }


def test_private_endpoint_opt_in_and_auth(tmp_path):
    settings = Settings(token="test-token", database=tmp_path / "state.sqlite")
    with TestClient(create_app(settings)) as client:
        assert client.post("/v1/daily-summary-drafts", json=request()).status_code == 401
        assert (
            client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH).status_code == 503
        )


def test_synthetic_replay_and_restart(tmp_path):
    with TestClient(app(tmp_path)) as client:
        first = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH).json()
        assert first["status"] == "draft" and first["new_provider_calls"] == 0
        assert first["requires_staff_review"] is True
        assert first["statistics"]["provider"] == "synthetic"
        replay = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH).json()
        assert replay["replayed"] and replay["statistics"] == first["statistics"]
        assert client.get("/v1/attempts/daily-one", headers=AUTH).json()["draft"] == first["draft"]
    with TestClient(app(tmp_path)) as client:
        assert client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH).json()[
            "replayed"
        ]


def test_empty_day_never_calls_provider(tmp_path):
    def forbidden(_):
        raise AssertionError("Empty day called provider")

    payload = request()
    payload["snapshot"]["events"] = []
    payload["snapshot_sha256"] = fingerprint(payload["snapshot"])
    with TestClient(
        app(tmp_path, forbidden, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        result = client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH).json()
        assert result["status"] == "empty" and result["statistics"] is None
        assert result["new_provider_calls"] == 0
        assert client.app.state.service.journal.maintenance()["drained"]


@pytest.mark.parametrize("change", ["duplicate", "private-field", "hash", "naive-time", "too-many"])
def test_bad_input_is_rejected_before_admission(tmp_path, change):
    payload = request()
    event = payload["snapshot"]["events"][0]
    if change == "duplicate":
        payload["snapshot"]["events"].append(copy.deepcopy(event))
    if change == "private-field":
        event["review_note"] = "private"
    if change == "hash":
        event["title"] = "changed"
    if change == "naive-time":
        event["start"] = "2026-10-10T12:00:00"
    if change == "too-many":
        payload["snapshot"]["events"] = [{**event, "id": f"synthetic-{n}"} for n in range(201)]
    if change != "hash":
        payload["snapshot_sha256"] = fingerprint(payload["snapshot"])
    with TestClient(app(tmp_path)) as client:
        assert (
            client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH).status_code == 422
        )
        assert client.app.state.service.journal.maintenance()["drained"]


def test_oversized_complete_input_not_truncated(tmp_path):
    payload = request()
    event = payload["snapshot"]["events"][0]
    payload["snapshot"]["events"] = [
        {**event, "id": f"synthetic-{n}", "route": "a" * 12000} for n in range(6)
    ]
    payload["snapshot_sha256"] = fingerprint(payload["snapshot"])
    with TestClient(app(tmp_path)) as client:
        reply = client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH)
        assert (
            reply.status_code == 422 and reply.json()["error"]["code"] == "summary_input_too_large"
        )
        assert client.app.state.service.journal.maintenance()["drained"]


@pytest.mark.parametrize(
    "content",
    [
        {"overview": [{"text": "A statement", "event_ids": ["absent"]}], "limitations": []},
        {
            "overview": [{"text": "A statement", "event_ids": ["synthetic-one", "synthetic-one"]}],
            "limitations": [],
        },
        {"tags": ["mobility"]},
    ],
)
def test_invalid_output_is_saved_as_failure_not_empty(tmp_path, content):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=completion(content))

    with TestClient(
        app(tmp_path, handler, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        result = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert result.status_code == 502 and result.json()["status"] == "failed"
        assert result.json()["draft"] is None
        assert result.json()["statistics"]["total_tokens"] == 130
        assert client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH).json()[
            "replayed"
        ]
        assert len(calls) == 1
        payload = request()
        for number in (2, 3):
            payload["request_id"] = f"attempt-{number}"
            result = client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH)
            assert result.status_code == 502
            assert result.json()["statistics"]["attempt_number"] == number
        payload["request_id"] = "attempt-4"
        assert (
            client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH).status_code == 429
        )
        assert len(calls) == 3


def test_provider_timeout_blocks_tags_and_summaries(tmp_path):
    def handler(_):
        raise httpx.ReadTimeout("test timeout")

    with TestClient(
        app(tmp_path, handler, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        result = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert result.status_code == 504 and result.json()["status"] == "unknown"
        assert client.get("/health/ready", headers=AUTH).status_code == 503
        assert (
            client.post(
                "/v1/tag-suggestions",
                headers=AUTH,
                json={
                    "request_id": "tag-one",
                    "job_id": "tag-job",
                    "source_version": "v1",
                    "event": {"id": "synthetic-tag", "title": "Für sichere Radwege"},
                },
            ).status_code
            == 409
        )


def test_shared_slot_prevents_concurrent_tag_and_summary(tmp_path):
    application = app(tmp_path)
    with TestClient(application):
        service, summary = application.state.service, application.state.summary

        class SlowProvider:
            async def draft(self, _):
                await asyncio.sleep(0.03)
                from service.summary.provider import SyntheticSummaryProvider

                return await SyntheticSummaryProvider().draft(_)

        summary.provider = SlowProvider()

        async def parallel():
            task = asyncio.create_task(summary.suggest(SummaryRequest.model_validate(request())))
            await asyncio.sleep(0.005)
            with pytest.raises(AdmissionError, match="inference_busy"):
                await service.suggest(
                    TagRequest.model_validate(
                        {
                            "request_id": "tag-one",
                            "job_id": "tag-job",
                            "source_version": "v1",
                            "event": {"id": "synthetic-tag", "title": "Für sichere Radwege"},
                        }
                    )
                )
            result, status = await task
            assert status == 200 and result["status"] == "draft"

        asyncio.run(parallel())


def test_known_returned_model_alias_retains_actual_identity(tmp_path):
    def handler(_):
        result = completion(
            {
                "overview": [
                    {"text": "Eine Demo für sichere Radwege.", "event_ids": ["synthetic-one"]}
                ],
                "limitations": [],
            }
        )
        result["model"] = "Qwen/Qwen3.6-35B-A3B"
        return httpx.Response(200, json=result)

    with TestClient(
        app(tmp_path, handler, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        reply = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert reply.status_code == 200
        stats = reply.json()["statistics"]
        assert stats["requested_model"] == "Qwen/Qwen3.6-35B-A3B-FP8"
        assert stats["returned_model"] == "Qwen/Qwen3.6-35B-A3B"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("envelope", "invalid_summary_envelope"),
        ("unfinished", "incomplete_summary_response"),
        ("model", "summary_model_mismatch"),
        ("json", "invalid_summary_json"),
        ("schema", "invalid_summary_schema"),
    ],
)
def test_summary_failures_explain_the_failed_check_without_output_text(tmp_path, change, code):
    def handler(_):
        body = completion(
            {
                "overview": [{"text": "Ein Entwurf.", "event_ids": ["synthetic-one"]}],
                "limitations": [],
            }
        )
        if change == "envelope":
            body["choices"] = []
        elif change == "unfinished":
            body["choices"][0]["finish_reason"] = "length"
        elif change == "model":
            body["model"] = "unexpected-model"
        elif change == "json":
            body["choices"][0]["message"]["content"] = "private model text, not JSON"
        elif change == "schema":
            body["choices"][0]["message"]["content"] = json.dumps({"summary": "private model text"})
        return httpx.Response(200, json=body)

    with TestClient(
        app(tmp_path, handler, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        reply = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert reply.status_code == 502
        assert reply.json()["error"]["code"] == code
        assert "private model text" not in reply.text
        assert reply.json()["statistics"]["total_tokens"] == 130
        assert client.get("/health/ready", headers=AUTH).status_code == 200
        assert client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH).json()[
            "replayed"
        ]


def test_connected_paragraph_can_cite_related_but_distinct_events(tmp_path):
    payload = request()
    event = copy.deepcopy(payload["snapshot"]["events"][0])
    event["id"] = "synthetic-two"
    payload["snapshot"]["events"].append(event)
    payload["snapshot_sha256"] = fingerprint(payload["snapshot"])

    def handler(_):
        return httpx.Response(
            200,
            json=completion(
                {
                    "overview": [
                        {
                            "text": "Two separate events concern safe cycle paths.",
                            "event_ids": ["synthetic-one", "synthetic-two"],
                        }
                    ],
                    "limitations": [],
                }
            ),
        )

    with TestClient(
        app(tmp_path, handler, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        reply = client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH)
        assert reply.status_code == 200
        assert reply.json()["draft"]["overview"][0]["event_ids"] == [
            "synthetic-one",
            "synthetic-two",
        ]


def test_service_owns_contract_and_english_example(tmp_path):
    with TestClient(app(tmp_path)) as client:
        assert client.get("/v1/daily-summary-contract").status_code == 401
        contract = client.get("/v1/daily-summary-contract", headers=AUTH).json()
        assert contract["config_id"] == "daily-summary-v1"
        assert contract["languages"] == ["de", "en"]
        payload = request()
        payload["snapshot"]["language"] = "en"
        payload["snapshot_sha256"] = fingerprint(payload["snapshot"])
        result = client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH).json()
        assert result["draft"]["overview"][0]["text"].startswith("Synthetic")
        assert result["config_sha256"] == contract["config_sha256"]
        assert (
            client.get("/v1/daily-summary-contract?config_id=missing", headers=AUTH).status_code
            == 404
        )


def test_example_facts_cannot_be_used_as_citations(tmp_path):
    content = {
        "overview": [{"text": "Fictional example", "event_ids": ["example-only"]}],
        "limitations": [],
    }
    with TestClient(
        app(
            tmp_path,
            lambda _: httpx.Response(200, json=completion(content)),
            mode="live",
            provider_key="fake",
            free_tier_confirmed=True,
        )
    ) as client:
        result = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert result.json()["error"]["code"] == "invalid_summary_citations"


def test_changed_product_fingerprint_is_rejected_before_inference(tmp_path):
    with TestClient(app(tmp_path)) as client:
        body = request()
        body["config_sha256"] = "0" * 64
        reply = client.post("/v1/daily-summary-drafts", json=body, headers=AUTH)
        assert reply.status_code == 422
        assert client.get("/v1/attempts/daily-one", headers=AUTH).status_code == 404


@pytest.mark.parametrize(
    "change",
    [
        "unknown-topic",
        "duplicate-id",
        "duplicate-label",
        "highlight-pair",
        "missing-field",
    ],
)
def test_briefing_requires_known_sources_and_one_highlight(tmp_path, change):
    content = {
        "overview": [{"text": "A daily paragraph.", "event_ids": ["synthetic-one"]}],
        "topics": [{"label": "Mobility", "event_ids": ["synthetic-one"]}],
        "highlight": None,
        "limitations": ["Registered feed only."],
    }
    payload = request()
    if change == "missing-topic":
        payload["snapshot"]["events"].append(
            {**payload["snapshot"]["events"][0], "id": "synthetic-two"}
        )
        payload["snapshot_sha256"] = fingerprint(payload["snapshot"])
    elif change == "unknown-topic":
        content["topics"][0]["event_ids"] = ["made-up"]
    elif change == "duplicate-id":
        content["topics"][0]["event_ids"].append("synthetic-one")
    elif change == "duplicate-label":
        content["topics"].append({"label": "MOBILITY", "event_ids": ["synthetic-one"]})
    elif change == "highlight-pair":
        content["highlight"] = {
            "text": "A highlight.",
            "event_ids": ["synthetic-one", "synthetic-one"],
        }

    def handler(_):
        body = completion(content)
        if change == "missing-field":
            body["choices"][0]["message"]["content"] = json.dumps(
                {"overview": content["overview"], "limitations": content["limitations"]}
            )
        return httpx.Response(200, json=body)

    with TestClient(
        app(tmp_path, handler, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        response = client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH)
        assert response.status_code == 502
        assert response.json()["draft"] is None
        assert client.get("/health/ready", headers=AUTH).status_code == 200


def test_contract_describes_model_independent_briefing(tmp_path):
    with TestClient(app(tmp_path)) as client:
        contract = client.get("/v1/daily-summary-contract", headers=AUTH).json()
        assert contract["draft_schema_version"] == 2
        assert contract["prompt_revision"] == 20
        assert contract["maximum_claim_length"] == 1000
        assert contract["maximum_claim_sources"] == 20
        assert contract["config_id"] == "daily-summary-v1"


@pytest.mark.parametrize(
    "ids, expected", [(["d001"], 200), (["d999"], 502), (["d001", "synthetic-one"], 502)]
)
def test_short_references_are_resolved_before_validation_and_storage(tmp_path, ids, expected):
    def handler(req):
        source = json.loads(json.loads(req.content)["messages"][-1]["content"])
        assert source["events"][0]["id"] == "d001"
        assert source["available_event_ids"] == ["d001"]
        content = {
            "overview": [{"text": "Ein Tagesthema.", "event_ids": ids}],
            "topics": [
                {"label": "Mobilität", "text": "Unter dem Motto sichere Radwege.", "event_ids": ids}
            ],
            "highlight": {"text": "Sichere Radwege.", "event_ids": ["d001"]},
            "limitations": ["Nur angemeldete Demonstrationen."],
        }
        return httpx.Response(200, json=completion(content))

    with TestClient(
        app(tmp_path, handler, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        reply = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert reply.status_code == expected
        if expected == 200:
            saved = client.get("/v1/attempts/daily-one", headers=AUTH).json()
            for claim in [
                *saved["draft"]["overview"],
                *saved["draft"]["topics"],
                saved["draft"]["highlight"],
            ]:
                assert claim["event_ids"] == ["synthetic-one"]
        else:
            assert reply.json()["error"]["code"] in {
                "invalid_summary_schema",
                "invalid_summary_citations",
            }


@pytest.mark.parametrize("assignments", [[], [[0]], [[2]], [[True]], [[1, 1]], [[]], [[1], [1]]])
def test_legacy_assignment_parser_rejects_invalid_topic_numbers(assignments):
    # Saved older configurations can still use the positional parser.
    config = SummaryConfig(Path(__file__).resolve().parents[3])
    payload = config.payload(SummaryRequest.model_validate(request()).snapshot)
    source = json.loads(payload["messages"][-1]["content"])
    source["required_event_ids"] = source.pop("available_event_ids")
    payload["messages"][-1]["content"] = json.dumps(source)
    topic_schema = payload["response_format"]["json_schema"]["schema"]["properties"]["topics"][
        "items"
    ]
    topic_schema["required"].remove("event_ids")
    body = {
        "overview": [],
        "topics": [{"label": "Mobility", "text": "Safe paths.", "include_in_briefing": True}],
        "assignments": assignments,
        "highlight": None,
        "limitations": [],
    }
    with pytest.raises(ProviderFailure):
        HetznerSummaryProvider.normalize_assignments(body, payload, {})


def test_unassigned_prose_is_omitted_without_changing_event_assignments(tmp_path):
    def handler(_):
        return httpx.Response(
            200,
            json=completion(
                {
                    "overview": [{"text": "Safe cycle routes.", "event_ids": ["d001"]}],
                    "topics": [
                        {"label": "Unassigned", "text": "Unsupported prose.", "event_ids": []},
                        {"label": "Mobility", "text": "Safe cycle routes.", "event_ids": ["d001"]},
                    ],
                    "limitations": ["Registered feed only."],
                }
            ),
        )

    with TestClient(
        app(tmp_path, handler, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        result = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert result.status_code == 200
        assert result.json()["draft"]["topics"] == [
            {
                "label": "Mobility",
                "text": "Safe cycle routes.",
                "event_ids": ["synthetic-one"],
                "include_in_briefing": True,
            }
        ]
        assert result.json()["statistics"]["total_tokens"] == 130


def test_short_highlight_title_survives_the_saved_response(tmp_path):
    content = {
        "overview": [{"text": "A daily introduction.", "event_ids": ["synthetic-one"]}],
        "topics": [
            {"label": "Mobility", "text": "Safe cycle paths.", "event_ids": ["synthetic-one"]}
        ],
        "highlight": {
            "title": "For safe cycle paths",
            "text": "A clear cycling demand.",
            "event_ids": ["synthetic-one"],
        },
        "limitations": ["Registered feed only."],
    }
    with TestClient(
        app(
            tmp_path,
            lambda _: httpx.Response(200, json=completion(content)),
            mode="live",
            provider_key="fake",
            free_tier_confirmed=True,
        )
    ) as client:
        result = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert result.status_code == 200
        assert result.json()["draft"]["highlight"]["title"] == "For safe cycle paths"
        saved = client.get("/v1/attempts/daily-one", headers=AUTH).json()
        assert saved["draft"]["highlight"] == result.json()["draft"]["highlight"]


def test_current_prompt_rejects_a_highlight_without_its_translatable_title(tmp_path):
    def handler(_):
        body = completion(
            {
                "overview": [{"text": "A daily introduction.", "event_ids": ["synthetic-one"]}],
                "highlight": {"text": "A concrete demand.", "event_ids": ["d001"]},
            }
        )
        content = json.loads(body["choices"][0]["message"]["content"])
        del content["highlight"]["title"]
        body["choices"][0]["message"]["content"] = json.dumps(content)
        return httpx.Response(200, json=body)

    with TestClient(
        app(tmp_path, handler, mode="live", provider_key="fake", free_tier_confirmed=True)
    ) as client:
        result = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert result.status_code == 502
        assert result.json()["error"]["code"] == "invalid_summary_schema"
        assert result.json()["draft"] is None
        assert client.get("/health/ready", headers=AUTH).status_code == 200


def test_internal_topic_keeps_its_source_ids_in_the_saved_draft(tmp_path):
    content = {
        "overview": [{"text": "Selected registered calls.", "event_ids": ["d001"]}],
        "topics": [
            {
                "label": "Interne Zuordnung",
                "text": "Internal assignment only.",
                "include_in_briefing": False,
                "event_ids": ["d001"],
            }
        ],
    }
    with TestClient(
        app(
            tmp_path,
            lambda _: httpx.Response(200, json=completion(content)),
            mode="live",
            provider_key="fake",
            free_tier_confirmed=True,
        )
    ) as client:
        result = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert result.status_code == 200
        topic = result.json()["draft"]["topics"][0]
        assert topic["include_in_briefing"] is False
        assert topic["event_ids"] == ["synthetic-one"]
        saved = client.get("/v1/attempts/daily-one", headers=AUTH).json()
        assert saved["draft"]["topics"] == [topic]


@pytest.mark.parametrize("flag", [None, "false", 0])
def test_invalid_topic_display_flags_are_rejected(tmp_path, flag):
    content = {
        "overview": [{"text": "Selected registered calls.", "event_ids": ["d001"]}],
        "topics": [
            {
                "label": "Interne Zuordnung",
                "text": "Internal assignment only.",
                "include_in_briefing": flag,
                "event_ids": ["d001"],
            }
        ],
    }
    with TestClient(
        app(
            tmp_path,
            lambda _: httpx.Response(200, json=completion(content)),
            mode="live",
            provider_key="fake",
            free_tier_confirmed=True,
        )
    ) as client:
        result = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert result.status_code == 502
        assert result.json()["error"]["code"] == "invalid_summary_schema"


def test_product_sends_a_complete_example_before_the_actual_snapshot():
    config = SummaryConfig(Path(__file__).resolve().parents[3])
    body = config.payload(SummaryRequest.model_validate(request()).snapshot)
    messages = body["messages"]
    assert body["chat_template_kwargs"]["enable_thinking"] is False
    assert [message["role"] for message in messages] == ["system", "user", "assistant", "user"]
    example_input, example_answer = [json.loads(message["content"]) for message in messages[1:3]]
    assert example_input["example_only"] is True
    assert all(
        identifier.startswith("EXAMPLE-") for identifier in example_input["available_event_ids"]
    )
    assert "assignments" not in example_answer
    assert len(example_answer["topics"]) == 4
    assert json.loads(messages[-1]["content"])["available_event_ids"] == ["d001"]
    assert (
        len(
            " ".join(
                [topic["text"] for topic in example_answer["topics"]]
                + [
                    example_answer["highlight"]["title"],
                    example_answer["highlight"]["text"],
                    *example_answer["limitations"],
                ]
            ).split()
        )
        <= 90
    )


@pytest.mark.parametrize(
    "problem",
    ["long-topic", "long-highlight", "long-overview", "example-phrase", "example-citation"],
)
def test_bad_writing_keeps_usage_and_releases_inference(tmp_path, problem):
    content = {
        "overview": [{"text": "Ein Überblick.", "event_ids": ["d001"]}],
        "topics": [
            {
                "label": "Mobilität",
                "text": "Sichere Radwege werden gefordert.",
                "event_ids": ["d001"],
            }
        ],
        "highlight": {
            "title": "Sichere Wege",
            "text": "Gefordert werden sichere Radwege.",
            "event_ids": ["d001"],
        },
        "limitations": ["Ausgewählte angemeldete Anliegen."],
    }
    expected = "summary_word_limit"
    if problem == "long-topic":
        content["topics"][0]["text"] = "Wort " * 95
    elif problem == "long-highlight":
        content["highlight"]["text"] = "Wort " * 95
    elif problem == "long-overview":
        content["overview"][0]["text"] = "Wort " * 41
    elif problem == "example-phrase":
        content["highlight"]["title"] = "LasstDieKuhLos"
        expected = "summary_example_leakage"
    else:
        content["highlight"]["event_ids"] = ["EXAMPLE-ANIMALS"]
        expected = "invalid_summary_citations"
    with TestClient(
        app(
            tmp_path,
            lambda _: httpx.Response(200, json=completion(content)),
            mode="live",
            provider_key="fake",
            free_tier_confirmed=True,
        )
    ) as client:
        response = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert response.status_code == 502
        result = response.json()
        assert result["draft"] is None
        assert result["error"]["code"] == expected
        assert result["statistics"]["total_tokens"] == 130
        assert result["statistics"]["outcome"] == "failed"
        assert client.get("/health/ready", headers=AUTH).status_code == 200
        saved = client.get("/v1/attempts/daily-one", headers=AUTH).json()
        assert saved["error"]["code"] == expected


@pytest.mark.parametrize("words, accepted", [(90, True), (91, False)])
def test_visible_prose_budget_boundary(tmp_path, words, accepted):
    content = {
        "overview": [{"text": "Ein Überblick.", "event_ids": ["d001"]}],
        "topics": [{"label": "Mobilität", "text": "Wort " * (words - 1), "event_ids": ["d001"]}],
        "limitations": ["Auswahl."],
    }
    with TestClient(
        app(
            tmp_path,
            lambda _: httpx.Response(200, json=completion(content)),
            mode="live",
            provider_key="fake",
            free_tier_confirmed=True,
        )
    ) as client:
        response = client.post("/v1/daily-summary-drafts", json=request(), headers=AUTH)
        assert response.status_code == (200 if accepted else 502)
        if not accepted:
            assert response.json()["error"]["code"] == "summary_word_limit"


def test_example_slogan_is_allowed_when_the_actual_cited_title_contains_it(tmp_path):
    payload = request()
    payload["snapshot"]["events"][0]["title"] = "LasstDieKuhLos - Anbindehaltung abschaffen!"
    payload["snapshot_sha256"] = fingerprint(payload["snapshot"])
    content = {
        "overview": [{"text": "Tierschutz steht zur Debatte.", "event_ids": ["d001"]}],
        "topics": [
            {
                "label": "Tierschutz",
                "text": "Ein Ende der Anbindehaltung wird gefordert.",
                "event_ids": ["d001"],
            }
        ],
        "highlight": {
            "title": "LasstDieKuhLos",
            "text": "Die Aktion fordert ein Ende der Anbindehaltung.",
            "event_ids": ["d001"],
        },
    }
    with TestClient(
        app(
            tmp_path,
            lambda _: httpx.Response(200, json=completion(content)),
            mode="live",
            provider_key="fake",
            free_tier_confirmed=True,
        )
    ) as client:
        response = client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["draft"]["highlight"]["title"] == "LasstDieKuhLos"


def test_editorial_selection_sends_the_full_day_but_cites_only_mentioned_events(tmp_path):
    payload = request()
    payload["snapshot"]["events"].append(
        {**payload["snapshot"]["events"][0], "id": "synthetic-two", "title": "Für bessere Schulen"}
    )
    payload["snapshot_sha256"] = fingerprint(payload["snapshot"])
    content = {
        "overview": [{"text": "Sichere Radwege.", "event_ids": ["d001"]}],
        "topics": [
            {
                "label": "Mobilität",
                "text": "Eine Aktion fordert sichere Radwege.",
                "event_ids": ["d001"],
            }
        ],
    }
    sources = []

    def handler(req):
        sources.append(json.loads(json.loads(req.content)["messages"][-1]["content"]))
        return httpx.Response(200, json=completion(content))

    with TestClient(
        app(
            tmp_path,
            handler,
            mode="live",
            provider_key="fake",
            free_tier_confirmed=True,
        )
    ) as client:
        response = client.post("/v1/daily-summary-drafts", json=payload, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["draft"]["topics"][0]["event_ids"] == ["synthetic-one"]
        assert len(sources[0]["events"]) == 2
        assert sources[0]["available_event_ids"] == ["d001", "d002"]
