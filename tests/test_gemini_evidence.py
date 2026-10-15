"""Offline checks for research provenance and complete cost estimates."""

import pytest

from notebooks.tools.gemini_evidence import evidence_from, request, usage_upper


def body(search=True, citation=True):
    return {
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "text",
                        "text": "Source-backed description",
                        "annotations": [
                            {"type": "url_citation", "url": "https://example.org/event"}
                        ]
                        if citation
                        else [],
                    }
                ],
            }
        ]
        + ([{"type": "google_search_call", "arguments": {"queries": ["event"]}}] if search else []),
    }


@pytest.mark.parametrize("search,citation", [(False, True), (True, False)])
def test_claim_or_url_alone_is_not_retrieval(search, citation):
    with pytest.raises(ValueError):
        evidence_from(body(search, citation))


def test_verified_provenance_is_not_verified_event_identity():
    assert evidence_from(body())["exact_event_verified"] is False


def test_price_uses_all_tokens_and_grounding():
    response = {"status": "completed", "usage": {"total_tokens": 1000}}
    assert usage_upper(response, "gemini-2.5-flash", research=True) == 37500
    assert usage_upper(response, "gemini-3.8-flash") == 3750
    assert usage_upper({"status": "completed"}, "gemini-2.5-flash") is None


def test_unpriced_model_rejected_before_network():
    with pytest.raises(ValueError):
        request(
            {"model": "unknown"},
            event_id="test",
            folder=None,
            guard=None,
            key=None,
            tags=[],
            live=True,
        )


def test_response_is_preserved_and_upper_estimate_cannot_exceed_ceiling(tmp_path, monkeypatch):
    import json

    import notebooks.tools.gemini_evidence as module
    from notebooks.tools.costs import BudgetGuard

    answer = {
        "status": "completed",
        "usage": {"total_tokens": 7000},
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": '{"tags":[]}'}]}],
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(answer).encode()

    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: Response())
    guard = BudgetGuard(
        tmp_path / "budget.sqlite", prior_total_microusd=0, prior_research_microusd=0
    )
    payload = {
        "model": "gemini-3.5-flash-lite",
        "input": "synthetic",
        "generation_config": {"max_output_tokens": 4096},
    }
    result = request(
        payload,
        event_id="synthetic",
        folder=tmp_path / "report",
        guard=guard,
        key="not-a-real-key",
        tags=[],
        live=True,
    )
    assert result["status"] == "ok"
    assert result["gross_upper_microusd"] <= result["maximum_microusd"]
    assert len(list((tmp_path / "report" / "attempts").glob("*-finished.json"))) == 1
    replay = request(
        payload,
        event_id="synthetic",
        folder=tmp_path / "report",
        guard=None,
        key=None,
        tags=[],
        live=False,
    )
    assert replay["cached"] and replay["gross_upper_microusd"] == result["gross_upper_microusd"]


def test_title_only_reservation_uses_explicit_run_and_nonresearch_budget(tmp_path, monkeypatch):
    import json
    import sqlite3

    import notebooks.tools.gemini_evidence as module
    from notebooks.tools.costs import BudgetGuard

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(
                {
                    "status": "completed",
                    "usage": {"total_tokens": 10},
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [{"type": "text", "text": '{"tags":[]}'}],
                        }
                    ],
                }
            ).encode()

    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: Response())
    path = tmp_path / "ledger.sqlite"
    guard = BudgetGuard(path, prior_total_microusd=0, prior_research_microusd=0)
    request(
        {
            "model": "gemini-3.8-flash",
            "input": "synthetic",
            "generation_config": {"max_output_tokens": 100},
        },
        event_id="test",
        folder=tmp_path / "report",
        guard=guard,
        key="fake",
        tags=[],
        live=True,
        run_id="broader-development",
        research_budget=False,
    )
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT run, research FROM reservations").fetchone() == (
            "broader-development",
            0,
        )
