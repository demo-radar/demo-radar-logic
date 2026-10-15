"""Protect review warnings against malformed or stale cached model output."""

import json

import pytest

from notebooks.tools.confidence import decode_confidence
from notebooks.tools.gem_profile import gem_request
from notebooks.tools.gemini import ENDPOINT
from notebooks.tools.hashes import fingerprint


def response(obj):
    return {
        "status": "completed",
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(obj)}]}],
    }


def test_omission_warning_does_not_replace_saved_tags():
    obj = {
        "support": "high",
        "completeness": "low",
        "cause": "rubric_boundary",
        "reason": "A second topic may be missing.",
    }
    assert decode_confidence(response(obj), {"politics"}) == {"predicted": [], "audit": obj}


@pytest.mark.parametrize(
    "change", [{"support": 0.9}, {"cause": "search"}, {"reason": ""}, {"tags": ["politics"]}]
)
def test_invalid_warning_is_not_treated_as_confident(change):
    obj = {"support": "high", "completeness": "high", "cause": "none", "reason": "Title is clear."}
    obj.update(change)
    with pytest.raises(ValueError):
        decode_confidence(response(obj), {"politics"})


def test_cache_is_revalidated_with_requested_decoder(tmp_path):
    payload = {"model": "gemini-3.8-flash", "generation_config": {"max_output_tokens": 1024}}
    identity = fingerprint({"endpoint": ENDPOINT, "payload": payload})
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / (identity + ".json")).write_text(
        json.dumps(
            {
                "request_sha256": identity,
                "status": "ok",
                "response": response({"support": "invalid"}),
            }
        )
    )
    with pytest.raises(ValueError):
        gem_request(
            payload,
            event_id="case",
            folder=tmp_path,
            key="",
            tags=[],
            guard=None,
            decoder=decode_confidence,
        )
