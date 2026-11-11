"""Model checks preserve approved aliases, usage and saved failures."""

import httpx
import pytest
from fastapi.testclient import TestClient

from service.app import create_app
from service.config import InferenceConfig
from service.providers.models import MODEL_CATALOG, ModelId
from service.summary.config import SummaryConfig
from tests.service.summary.test_api import completion as summary_completion
from tests.service.summary.test_api import request as summary_request
from tests.service.test_api import AUTH, ROOT, completion, request, settings


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    price = MODEL_CATALOG[ModelId.OPENAI_SOL].pricing
    monkeypatch.setitem(price, "valid_from", "2000-01-01")
    monkeypatch.setitem(price, "valid_until", "2100-12-31")
    return settings(
        tmp_path,
        mode="live",
        provider_key="synthetic-hetzner-key",
        free_tier_confirmed=True,
        openai_enabled=True,
        openai_key="synthetic-openai-key",
        openai_account="openai:synthetic",
        paid_run_usd="1",
        paid_period_usd="1",
        paid_account_usd="1",
        summary_enabled=True,
    )


def task_request(task, provider):
    if task == "tagging":
        config = InferenceConfig(ROOT, f"{'qwen' if provider == 'hetzner' else provider}-v4-v1")
        return "/v1/tag-suggestions", {**request(), "model_id": config.version}, config
    config = SummaryConfig(ROOT, f"{provider}-daily-v1")
    return (
        "/v1/daily-summary-drafts",
        {**summary_request(), "model_id": config.version, "config_sha256": config.sha256},
        config,
    )


def response_body(task, returned_model):
    body = (
        completion()
        if task == "tagging"
        else summary_completion(
            {
                "overview": [{"text": "Eine Demo für sichere Radwege.", "event_ids": ["d001"]}],
                "limitations": [],
            }
        )
    )
    body["model"] = returned_model
    return body


@pytest.mark.parametrize("task", ["tagging", "summary"])
@pytest.mark.parametrize(
    ("provider", "returned_model"),
    [
        ("hetzner", ModelId.QWEN),
        ("hetzner", "Qwen/Qwen3.6-35B-A3B"),
        ("openai", ModelId.OPENAI_SOL),
    ],
)
def test_approved_models_keep_actual_identity_and_replay(runtime, task, provider, returned_model):
    endpoint, data, config = task_request(task, provider)
    calls = []

    def respond(req):
        calls.append(req)
        assert (
            str(req.url)
            == {
                "hetzner": "https://inference.hetzner.com/v1/chat/completions",
                "openai": "https://api.openai.com/v1/chat/completions",
            }[provider]
        )
        return httpx.Response(200, json=response_body(task, returned_model))

    with TestClient(create_app(runtime, transport=httpx.MockTransport(respond))) as client:
        reply = client.post(endpoint, headers=AUTH, json=data)
        assert reply.status_code == 200, reply.text
        stats = reply.json()["statistics"]
        assert stats["requested_model"] == config.model
        assert stats["returned_model"] == returned_model
        assert client.post(endpoint, headers=AUTH, json=data).json()["replayed"]
        assert len(calls) == 1


@pytest.mark.parametrize("task", ["tagging", "summary"])
@pytest.mark.parametrize("provider", ["hetzner", "openai"])
@pytest.mark.parametrize(
    "returned_model",
    [None, "", 123, [], {}, "other-model", "other-provider", "gpt-6.1-sol-extra"],
)
def test_unapproved_models_save_failure_and_usage_without_retry(
    runtime, task, provider, returned_model
):
    endpoint, data, _ = task_request(task, provider)
    if returned_model == "other-provider":
        returned_model = ModelId.OPENAI_SOL if provider == "hetzner" else "Qwen/Qwen3.6-35B-A3B"
    body = response_body(task, returned_model)
    calls = []

    def respond(req):
        calls.append(req)
        return httpx.Response(200, json=body)

    app = create_app(runtime, transport=httpx.MockTransport(respond))
    with TestClient(app) as client:
        reply = client.post(endpoint, headers=AUTH, json=data)
        assert reply.status_code == 502, reply.text
        result = reply.json()
        assert result["error"]["code"] == (
            "invalid_provider_response" if task == "tagging" else "summary_model_mismatch"
        )
        stats = result["statistics"]
        assert stats["total_tokens"] == body["usage"]["total_tokens"]
        assert stats["returned_model"] == (
            returned_model if isinstance(returned_model, str) else None
        )
        assert client.post(endpoint, headers=AUTH, json=data).json()["replayed"]
        assert len(calls) == 1
        if provider == "openai":
            with app.state.service.journal.connection() as db:
                spending = db.execute("SELECT * FROM spending").fetchone()
                assert spending["charged"] is None and spending["reserved"] > 0
