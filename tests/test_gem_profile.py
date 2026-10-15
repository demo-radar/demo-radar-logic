"""Gem output validation, native-search provenance and budget reconciliation."""

import json
import sqlite3

import pytest

from notebooks.tools.costs import BudgetGuard
from notebooks.tools.gem_profile import decode_gem, gem_request, search_trace, usage_cost


def response(tokens=100, search=False):
    data = {
        "tags": ["mobility"],
        "confidence": 0.8,
        "reason": "Bicycle lanes",
        "needs_review": False,
        "proposals": [],
    }
    return {
        "status": "completed",
        "usage": {"total_tokens": tokens},
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "text",
                        "text": "```json\n" + json.dumps(data) + "\n```\nExplanation",
                        "annotations": [{"type": "url_citation", "url": "https://example.org"}],
                    }
                ],
            }
        ]
        + (
            [{"type": "google_search_call", "arguments": {"queries": ["one", "two"]}}]
            if search
            else []
        ),
    }


def test_gem_json_and_optional_explanation():
    result = decode_gem(response(), ["mobility"])
    assert result["predicted"] == ["mobility"]
    assert result["gem"]["reason"] == "Bicycle lanes"
    with pytest.raises(ValueError):
        decode_gem(response(), ["environment"])


def test_citations_are_not_search_execution():
    assert not search_trace(response())["search_executed"]
    assert search_trace(response(search=True))["search_executed"]
    assert usage_cost(response(search=True), True) == 28375
    assert usage_cost({"usage": {}}, True) is None


def test_native_usage_above_allowance_is_not_clamped(tmp_path, monkeypatch):
    import notebooks.tools.gem_profile as module

    body = response(100000, search=True)

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(body).encode()

    monkeypatch.setattr(module, "urlopen", lambda *a, **k: Reply())
    ledger = tmp_path / "ledger.sqlite"
    guard = BudgetGuard(ledger, prior_total_microusd=0, prior_research_microusd=0)
    payload = {
        "model": "gemini-3.8-flash",
        "input": "synthetic",
        "tools": [{"type": "google_search"}],
        "generation_config": {"max_output_tokens": 4096},
    }
    result = gem_request(
        payload,
        event_id="synthetic",
        folder=tmp_path / "run",
        key="fake",
        tags=["mobility"],
        guard=guard,
        live=True,
    )
    assert result["gross_upper_microusd"] > result["reservation_microusd"]
    with sqlite3.connect(ledger) as db:
        assert (
            db.execute("SELECT SUM(effective_amount) FROM effective_reservations").fetchone()[0]
            == result["gross_upper_microusd"]
        )
    replay = gem_request(
        payload,
        event_id="synthetic",
        folder=tmp_path / "run",
        key=None,
        tags=["mobility"],
        guard=None,
        live=False,
    )
    assert replay["cached"] and replay["predicted"] == ["mobility"]


def test_unknown_usage_stops_more_live_calls(tmp_path, monkeypatch):
    import notebooks.tools.gem_profile as module

    body = response()
    body["usage"] = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(body).encode()

    monkeypatch.setattr(module, "urlopen", lambda *a, **k: Reply())
    guard = BudgetGuard(
        tmp_path / "ledger.sqlite", prior_total_microusd=0, prior_research_microusd=0
    )
    payload = {
        "model": "gemini-3.8-flash",
        "input": "synthetic",
        "generation_config": {"max_output_tokens": 4096},
    }
    result = gem_request(
        payload,
        event_id="one",
        folder=tmp_path / "run",
        key="fake",
        tags=["mobility"],
        guard=guard,
        live=True,
    )
    assert result["accounting_pending"]
    with pytest.raises(ValueError, match="Reconcile"):
        gem_request(
            {**payload, "input": "another"},
            event_id="two",
            folder=tmp_path / "run",
            key="fake",
            tags=["mobility"],
            guard=guard,
            live=True,
        )


def test_budget_pause_does_not_send_request(tmp_path, monkeypatch):
    import notebooks.tools.gem_profile as module

    def unexpected_call(*args, **kwargs):
        raise AssertionError("A rejected reservation must not reach the provider")

    monkeypatch.setattr(module, "urlopen", unexpected_call)
    guard = BudgetGuard(
        tmp_path / "ledger.sqlite",
        prior_total_microusd=50_000_000,
        prior_research_microusd=0,
    )
    result = gem_request(
        {
            "model": "gemini-3.8-flash",
            "input": "synthetic",
            "generation_config": {"max_output_tokens": 4096},
        },
        event_id="synthetic",
        folder=tmp_path / "run",
        key="fake",
        tags=["mobility"],
        guard=guard,
        live=True,
    )
    assert result["status"] == "budget_paused"
    assert not list((tmp_path / "run").glob("attempts/*"))
