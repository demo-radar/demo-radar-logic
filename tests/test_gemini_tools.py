"""Provider provenance and replay checks without live requests."""

import pytest

from notebooks.tools.gemini import decode_result, gemini_request


def response(text, extra=None):
    return {
        "status": "completed",
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}]
        + (extra or []),
    }


def test_text_claim_is_not_search_execution():
    decoded = decode_result(response('{"tags":["environment"]}'), ["environment"])
    assert decoded["predicted"] == ["environment"]
    assert not decoded["search_executed"]


def test_real_search_trace_and_fenced_json():
    decoded = decode_result(
        response(
            '```json\n{"tags":[]}\n```',
            [{"type": "google_search_call", "arguments": {"queries": ["public event"]}}],
        ),
        ["environment"],
    )
    assert decoded["search_executed"]
    assert decoded["queries"] == ["public event"]


@pytest.mark.parametrize(
    "text",
    [
        '{"tags":["made-up"]}',
        '{"tags":[],"reason":"extra"}',
        '{"tags":["environment","environment"]}',
    ],
)
def test_invalid_tags_are_not_repaired(text):
    with pytest.raises(ValueError):
        decode_result(response(text), ["environment"])


def test_incomplete_response_rejected():
    with pytest.raises(ValueError):
        decode_result({"status": "in_progress"}, ["environment"])


def test_replay_without_cache_does_not_reserve_or_send(tmp_path):
    result = gemini_request(
        {"model": "gemini-2.5-flash"},
        event_id="synthetic",
        tags=[],
        folder=tmp_path,
        key=None,
        guard=None,
        live=False,
    )
    assert result["status"] == "missing_cache"


def test_saved_cooldown_blocks_send_before_reservation(tmp_path):
    import json
    import time

    (tmp_path / "cooldown.json").write_text(json.dumps({"retry_at_epoch": time.time() + 3600}))
    result = gemini_request(
        {"model": "gemini-2.5-flash"},
        event_id="synthetic",
        tags=[],
        folder=tmp_path,
        key="not-a-real-key",
        guard=None,
        live=True,
    )
    assert result["status"] == "rate_limit_paused"


def test_other_models_require_their_own_pricing():
    with pytest.raises(ValueError, match="priced"):
        gemini_request(
            {"model": "unpriced-model"},
            event_id="synthetic",
            tags=[],
            folder=None,
            key=None,
            guard=None,
            live=True,
        )
