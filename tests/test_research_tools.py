"""Test real-search provenance, replay and rate-limit behavior without network calls."""

import json

import pytest

from notebooks.tools.research import research_evidence

BODY = {
    "model": "test-model",
    "choices": [
        {
            "finish_reason": "stop",
            "message": {
                "content": "Background only. https://example.org/source",
                "executed_tools": [
                    {
                        "name": "browser.search",
                        "search_results": {"results": [{"url": "https://example.org/source"}]},
                    }
                ],
            },
        }
    ],
}


def test_rejects_claimed_search_without_tool_execution():
    body = {"choices": [{"finish_reason": "stop", "message": {"content": "I searched the web"}}]}
    with pytest.raises(ValueError, match="No browser.search"):
        research_evidence(body)


def test_browser_actions_can_have_null_search_results():
    body = json.loads(json.dumps(BODY))
    body["choices"][0]["message"]["executed_tools"].append(
        {"name": "browser.find", "search_results": None}
    )
    assert research_evidence(body)["source_urls"] == ["https://example.org/source"]
