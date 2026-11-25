"""OpenAI uses paid admission and the same task validation and replay behavior."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from service.app import create_app
from service.config import InferenceConfig
from service.providers.hetzner import HetznerProvider
from service.providers.models import MODEL_CATALOG, ModelId
from service.summary.config import SummaryConfig
from tests.service.summary.test_api import request as summary_request
from tests.service.test_api import AUTH, ROOT, request, settings

SOL_62_TAGGING = "openai-sol-6-2-v4-v1"
SOL_62_SUMMARY = "openai-sol-6-2-daily-v1"
OPENAI_TAGGING_MODELS = [
    ("openai-v4-v1", ModelId.OPENAI_SOL),
    (SOL_62_TAGGING, ModelId.OPENAI_SOL_62),
]


@pytest.fixture(autouse=True)
def reviewed_price(monkeypatch):
    for _, model in OPENAI_TAGGING_MODELS:
        monkeypatch.setitem(MODEL_CATALOG[model].pricing, "valid_from", "2000-01-01")
        monkeypatch.setitem(MODEL_CATALOG[model].pricing, "valid_until", "2100-12-31")


def runtime(tmp_path, **changes):
    return settings(
        tmp_path,
        mode="live",
        openai_enabled=True,
        openai_key="synthetic-openai-key",
        openai_account="openai:synthetic",
        paid_run_usd="1",
        paid_period_usd="1",
        paid_account_usd="1",
        summary_enabled=True,
        **changes,
    )


def tag_request(profile_id="openai-v4-v1"):
    return {**request(), "model_id": profile_id}


def answer(content=None, *, model=ModelId.OPENAI_SOL):
    return {
        "model": model,
        "id": "synthetic-completion",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps(content or {"tags": ["mobility"]})},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.mark.parametrize(("profile_id", "model"), OPENAI_TAGGING_MODELS)
def test_tagging_replays_without_another_paid_call(tmp_path, profile_id, model):
    calls = []
    config = InferenceConfig(ROOT, profile_id)
    data = tag_request(profile_id)
    data["execution"] = {
        "task": "tagging",
        "origin": "manual_api",
        "profile_sha256": config.sha256,
    }

    def respond(req):
        calls.append(req)
        assert str(req.url) == "https://api.openai.com/v1/chat/completions"
        assert req.headers["authorization"] == "Bearer synthetic-openai-key"
        payload = json.loads(req.content)
        assert payload["model"] == model
        assert payload["store"] is False and payload["reasoning_effort"] == "low"
        assert "temperature" not in payload and "chat_template_kwargs" not in payload
        return httpx.Response(200, json=answer(model=model))

    app = create_app(runtime(tmp_path), transport=httpx.MockTransport(respond))
    with TestClient(app) as client:
        first = client.post("/v1/tag-suggestions", headers=AUTH, json=data)
        assert first.status_code == 200, first.text
        assert first.json()["config_sha256"] == config.sha256
        assert first.json()["statistics"]["provider"] == "openai"
        assert first.json()["statistics"]["returned_model"] == model
        replay = client.post("/v1/tag-suggestions", headers=AUTH, json=data)
        assert replay.json()["replayed"] and len(calls) == 1
        with app.state.service.journal.connection() as db:
            saved = db.execute("SELECT * FROM spending").fetchone()
            assert json.loads(saved["policy"])["model"] == model
            assert saved["reserved"] >= saved["charged"] == 75


@pytest.mark.parametrize(
    ("profile_id", "model"),
    [("openai-daily-v1", ModelId.OPENAI_SOL), (SOL_62_SUMMARY, ModelId.OPENAI_SOL_62)],
)
def test_summary_keeps_the_shared_example_and_schema(tmp_path, profile_id, model):
    config = SummaryConfig(ROOT, profile_id)
    legacy = SummaryConfig(ROOT, "openai-daily-v1")
    assert legacy.sha256 == "13b1bf2cac49b9f9769ef85b17a6ac3e7ab8c1b4e5d0c5607e057e16df20de20"
    assert config.model == model
    tagging = InferenceConfig(ROOT, SOL_62_TAGGING)
    data = summary_request()
    data.update(model_id=config.version, config_sha256=config.sha256)
    draft = {
        "overview": [{"text": "Eine Aktion fordert sichere Radwege.", "event_ids": ["d001"]}],
        "topics": [{"label": "Mobilität", "text": "Sichere Radwege.", "event_ids": ["d001"]}],
        "highlight": None,
        "limitations": ["Nur angemeldete Versammlungen."],
    }

    def respond(req):
        payload = json.loads(req.content)
        assert payload["model"] == model
        assert payload["reasoning_effort"] == "low" and payload["store"] is False
        assert any(message["role"] == "assistant" for message in payload["messages"])
        assert payload["response_format"]["type"] == "json_schema"
        return httpx.Response(200, json=answer(draft, model=model))

    with TestClient(
        create_app(runtime(tmp_path), transport=httpx.MockTransport(respond))
    ) as client:
        profiles = client.get("/v1/task-profiles", headers=AUTH).json()["profiles"]
        assert {(p["task"], p["profile_id"]) for p in profiles if p["model"] == tagging.model} == {
            ("tagging", tagging.version),
            ("daily-summary", SOL_62_SUMMARY),
        }
        denied = client.post(
            "/v1/daily-summary-drafts",
            headers=AUTH,
            json={**data, "model_id": tagging.version, "config_sha256": tagging.sha256},
        )
        assert denied.status_code == 422 and denied.json()["inference_admitted"] is False
        reply = client.post("/v1/daily-summary-drafts", headers=AUTH, json=data)
        assert reply.status_code == 200, reply.text
        assert reply.json()["statistics"]["provider"] == "openai"
        assert reply.json()["statistics"]["returned_model"] == model
        assert reply.json()["config_sha256"] == config.sha256


@pytest.mark.parametrize(
    "changes",
    [
        {"openai_enabled": False},
        {"openai_key": ""},
        {"openai_account": ""},
        {"paid_run_usd": "0.000001"},
    ],
)
@pytest.mark.parametrize(("profile_id", "_model"), OPENAI_TAGGING_MODELS)
def test_disabled_or_unfunded_profile_never_calls_provider(tmp_path, changes, profile_id, _model):
    from dataclasses import replace

    calls = []

    def respond(req):
        calls.append(req)
        return httpx.Response(200, json=answer())

    with TestClient(
        create_app(
            replace(
                runtime(tmp_path),
                provider_key="synthetic-hetzner",
                free_tier_confirmed=True,
                **changes,
            ),
            transport=httpx.MockTransport(respond),
        )
    ) as client:
        reply = client.post("/v1/tag-suggestions", headers=AUTH, json=tag_request(profile_id))
        assert reply.status_code != 200 and not calls


@pytest.mark.parametrize(("profile_id", "model"), OPENAI_TAGGING_MODELS)
@pytest.mark.parametrize("outcome", ["rate_limit", "timeout", "truncated", "wrong_model"])
def test_failed_calls_do_not_retry_or_switch_vendor(tmp_path, outcome, profile_id, model):
    calls = []

    def respond(req):
        calls.append(req)
        if outcome == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=req)
        if outcome == "rate_limit":
            return httpx.Response(429, headers={"Retry-After": "10"})
        body = answer(model=model)
        if outcome == "truncated":
            body["choices"][0]["finish_reason"] = "length"
        else:
            body["model"] = (
                ModelId.OPENAI_SOL if model == ModelId.OPENAI_SOL_62 else ModelId.OPENAI_SOL_62
            )
        return httpx.Response(200, json=body)

    with TestClient(
        create_app(runtime(tmp_path), transport=httpx.MockTransport(respond))
    ) as client:
        reply = client.post("/v1/tag-suggestions", headers=AUTH, json=tag_request(profile_id))
        assert reply.status_code in {429, 502, 504}, reply.text
        assert len(calls) == 1
        assert "synthetic-openai-key" not in reply.text


def test_historical_hetzner_profile_uses_the_new_transport_url():
    config = InferenceConfig(ROOT)
    original = config.sha256
    adapter = HetznerProvider(None, config, "synthetic")
    assert config.endpoint == HetznerProvider.LEGACY_ENDPOINT
    assert adapter.ENDPOINT == "https://inference.hetzner.com/v1/chat/completions"
    assert InferenceConfig(ROOT).sha256 == original
