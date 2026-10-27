"""Strict output models preserve evidence and supported historical formats."""

import asyncio
import copy
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from service.config import InferenceConfig
from service.contracts import AttemptStatistics, ErrorDetail
from service.inference.contracts import ProfileCatalog, ProfileDescriptor
from service.inference.profiles import describe_profile
from service.providers.base import ProviderFailure
from service.providers.gemini import GeminiProvider
from service.providers.gemini_contracts import GeminiMetadata, GeminiTokenCount, GeminiUsage
from service.summary.config import SummaryConfig
from service.summary.contracts import SummaryDraft, SummaryDraftV2, SummaryResponse
from service.summary.provider import SummaryParser
from tests.service.test_api import ROOT


def statistics():
    return {
        "schema_version": 1,
        "attempt_id": "synthetic-attempt",
        "attempt_number": 1,
        "provider": "synthetic",
        "requested_model": "synthetic-model",
        "returned_model": None,
        "provider_request_id": None,
        "started_at": "2026-10-27T10:00:00Z",
        "finished_at": "2026-10-27T10:00:01Z",
        "duration_seconds": 1,
        "provider_call_occurred": False,
        "outcome": "ok",
        "usage_raw": None,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "token_semantics": "unknown",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"attempt_number": 0},
        {"input_tokens": False},
        {"output_tokens": "12"},
        {"total_tokens": -1},
        {"duration_seconds": float("nan")},
        {"provider_call_occurred": 1},
        {"started_at": "2026-10-27T10:00:00"},
        {"finished_at": "2020-01-01T00:00:00Z"},
    ],
)
def test_attempt_statistics_reject_coercion_and_impossible_values(change):
    with pytest.raises(ValidationError):
        AttemptStatistics.model_validate({**statistics(), **change})


def test_unknown_usage_stays_null_and_timestamps_are_not_rewritten():
    source = statistics()
    result = AttemptStatistics.model_validate(source).model_dump()
    assert result["input_tokens"] is None and result["total_tokens"] is None
    assert result["started_at"] == source["started_at"]
    assert result["finished_at"] == source["finished_at"]
    del source["input_tokens"]
    with pytest.raises(ValidationError):
        AttemptStatistics.model_validate(source)


@pytest.mark.parametrize(
    "change",
    [
        {"http_status": 200},
        {"http_status": True},
        {"retry_after_seconds": -1},
        {"retry_after_seconds": float("inf")},
        {"retryable": "true"},
    ],
)
def test_error_details_keep_strict_status_and_retry_fields(change):
    with pytest.raises(ValidationError):
        ErrorDetail.model_validate(
            {
                "code": "provider_pacing",
                "message": "Wait before retrying.",
                "http_status": 429,
                **change,
            }
        )
    assert (
        ErrorDetail(
            code="provider_pacing",
            message="Wait before retrying.",
            http_status=429,
            retry_after_seconds=172800,
        ).retry_after_seconds
        == 172800
    )


def test_catalog_validation_does_not_add_defaults_or_change_fingerprints():
    tag = describe_profile("tagging", InferenceConfig(ROOT))
    summary = describe_profile("daily-summary", SummaryConfig(ROOT))
    original = copy.deepcopy([tag, summary])
    result = ProfileCatalog(
        schema_version=1, profiles=[tag, summary], unavailable_tasks=["routes"]
    ).model_dump(mode="json", exclude_unset=True)
    assert result["profiles"] == original
    assert "max_attempts" not in result["profiles"][1]["contract"]
    with pytest.raises(ValidationError):
        ProfileCatalog(schema_version=1, profiles=[tag, tag], unavailable_tasks=["routes"])
    invalid = copy.deepcopy(tag)
    invalid["contract"]["credential"] = "synthetic-secret-must-not-be-published"
    with pytest.raises(ValidationError):
        ProfileDescriptor.model_validate(invalid)


def test_version_two_requires_fields_while_legacy_drafts_remain_readable():
    legacy = {
        "overview": [{"text": "A cycle-lane gathering.", "event_ids": ["d001"]}],
        "limitations": [],
    }
    assert SummaryDraft.model_validate(legacy).highlight is None
    with pytest.raises(ValidationError):
        SummaryDraftV2.model_validate(legacy)
    current = {
        **legacy,
        "topics": [{"label": "Mobility", "event_ids": ["d001"]}],
        "highlight": None,
        "limitations": ["Registered events only."],
    }
    assert SummaryDraftV2.model_validate(current).overview[0].event_ids == ["d001"]
    with pytest.raises(ValidationError):
        SummaryDraftV2.model_validate({**current, "limitations": []})


@pytest.mark.parametrize("assignments", [[[True]], [[1, 1]], [[2]], [], [[1], [1]]])
def test_assignment_schema_keeps_source_count_and_topic_number_rules(assignments):
    body = {
        "overview": [{"text": "A cycle-lane gathering.", "event_ids": ["d001"]}],
        "topics": [{"label": "Mobility", "text": "Safe cycle lanes."}],
        "highlight": None,
        "limitations": [],
        "assignments": [[1]],
    }
    payload = {
        "messages": [{"content": json.dumps({"required_event_ids": ["d001"]})}],
        "response_format": {
            "json_schema": {
                "schema": {"properties": {"topics": {"items": {"required": ["label", "text"]}}}}
            }
        },
    }
    original = copy.deepcopy(body)
    mapped = SummaryParser.normalize_assignments(body, payload, {})
    assert mapped["topics"][0]["event_ids"] == ["d001"]
    assert body == original
    with pytest.raises(ProviderFailure):
        SummaryParser.normalize_assignments({**body, "assignments": assignments}, payload, {})


def test_gemini_bad_content_preserves_usage_and_provider_identity():
    config = InferenceConfig(ROOT, "gemini-v4-v1")
    body = {
        "modelVersion": config.model,
        "responseId": "synthetic-provider-id",
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 3,
            "thoughtsTokenCount": 2,
            "totalTokenCount": 15,
        },
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": 123}]}}],
    }
    original = copy.deepcopy(body)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
        ) as client:
            provider = GeminiProvider(client, config, "synthetic-secret")
            with pytest.raises(ProviderFailure) as failed:
                await provider.response_body(config.payload("Invented cycling slogan"))
            assert failed.value.code == "invalid_provider_response"
            evidence = failed.value.metadata
            assert evidence["model"] == config.model
            assert evidence["id"] == "synthetic-provider-id"
            assert evidence["usage"]["total_tokens"] == 15
            assert evidence["usage"]["completion_tokens"] == 5
            assert evidence["usage"]["gemini"] == original["usageMetadata"]

    asyncio.run(run())
    assert body == original


@pytest.mark.parametrize("count", [True, "12", -1])
def test_bad_gemini_counts_are_unknown_but_cannot_admit_generation(count):
    usage = GeminiUsage.model_validate({"promptTokenCount": count})
    assert usage.prompt_tokens is None
    with pytest.raises(ValidationError):
        GeminiTokenCount.model_validate({"totalTokens": count})
    metadata = GeminiMetadata.model_validate({"usageMetadata": {"totalTokenCount": 12}})
    evidence = metadata.evidence({"usageMetadata": {"totalTokenCount": 12}})
    assert evidence["usage"]["completion_tokens"] is None
    assert evidence["usage"]["total_tokens"] == 12


@pytest.mark.parametrize("value", [False, 1, "true"])
def test_responses_do_not_coerce_review_acknowledgement(value):
    body = {
        "request_id": "synthetic-request",
        "job_id": "synthetic-job",
        "date": "2026-10-27",
        "snapshot_sha256": "a" * 64,
        "config_version": "synthetic-config",
        "config_sha256": "b" * 64,
        "mode": "demo",
        "status": "empty",
        "draft": None,
        "requires_staff_review": True,
        "error": None,
        "replayed": False,
        "new_provider_calls": 0,
        "statistics": None,
    }
    assert SummaryResponse.model_validate(body).requires_staff_review is True
    with pytest.raises(ValidationError):
        SummaryResponse.model_validate({**body, "requires_staff_review": value})


def test_summary_schema_errors_do_not_log_generated_field_names(caplog):
    parser = SummaryParser(
        SimpleNamespace(
            data={"draft_schema_version": 2},
            model="synthetic-model",
        )
    )
    draft = {
        "overview": [{"text": "A cycling gathering.", "event_ids": ["synthetic-one"]}],
        "topics": [],
        "highlight": None,
        "limitations": ["Registered events only."],
        "private_generated_field_name": "private_generated_prose",
    }
    body = {
        "model": "synthetic-model",
        "id": "synthetic-provider",
        "usage": {"total_tokens": 12},
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(draft)}}],
    }
    with pytest.raises(ProviderFailure) as failure:
        parser.parse_draft(body, {})
    assert failure.value.metadata["usage"]["total_tokens"] == 12
    assert "extra_forbidden" in caplog.text
    assert "private_generated_field_name" not in caplog.text
    assert "private_generated_prose" not in caplog.text
