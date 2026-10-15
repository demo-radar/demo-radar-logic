"""The experimental three-tag validator must not loosen the approved v1 policy."""

import json

import pytest

from notebooks.tools.gemini import decode_result
from notebooks.tools.hosted import parse_llm_tags
from notebooks.tools.tag_policy import parse_tied_tags

TAGS = {"housing", "environment", "politics"}


def answer(tags, tie=False, reason=""):
    return json.dumps({"tags": tags, "tie": tie, "tie_reason": reason})


def test_three_requires_explanation_and_keeps_v1_strict():
    values = ["housing", "environment", "politics"]
    assert (
        parse_tied_tags(answer(values, True, "All three demands appear in the title"), TAGS)
        == values
    )
    with pytest.raises(ValueError):
        parse_llm_tags(json.dumps({"tags": values}), TAGS)


@pytest.mark.parametrize(
    "content",
    [
        answer(["housing"] * 3, True, "duplicate"),
        answer(["unknown"]),
        answer(["housing", "environment", "politics"]),
        answer(["housing", "environment", "politics"], True, "  "),
        answer(["housing"], True, "uncertain"),
        answer(["housing"], False, "unexpected"),
        answer([], 0),
        json.dumps({"tags": [], "tie": False}),
    ],
)
def test_rejects_invalid_tie_contract(content):
    with pytest.raises(ValueError):
        parse_tied_tags(content, TAGS)


def test_gemini_uses_explicit_parser_but_default_stays_two_tags():
    content = answer(["housing", "environment", "politics"], True, "Three central demands")
    body = {
        "status": "completed",
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": content}]}],
    }
    assert len(decode_result(body, TAGS, content_parser=parse_tied_tags)["predicted"]) == 3
    with pytest.raises(ValueError):
        decode_result(body, TAGS)
    body["status"] = "incomplete"
    with pytest.raises(ValueError):
        decode_result(body, TAGS, content_parser=parse_tied_tags)


def test_gemini_replay_revalidates_experimental_schema(tmp_path):
    from notebooks.tools.gemini import ENDPOINT
    from notebooks.tools.gemini_evidence import request
    from notebooks.tools.hashes import fingerprint

    payload = {"model": "gemini-3.8-flash", "input": "synthetic tie example"}
    identity = fingerprint({"endpoint": ENDPOINT, "payload": payload})
    folder = tmp_path / "cache"
    folder.mkdir()
    values = ["housing", "environment", "politics"]
    response = {
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {"type": "text", "text": answer(values, True, "Three demands in title")}
                ],
            }
        ],
    }
    (folder / (identity + ".json")).write_text(
        json.dumps(
            {"request_sha256": identity, "status": "ok", "response": response, "predicted": []}
        )
    )
    result = request(
        payload,
        event_id="synthetic",
        folder=tmp_path,
        guard=None,
        key=None,
        tags=TAGS,
        content_parser=parse_tied_tags,
    )
    assert result["cached"] and result["predicted"] == values
    with pytest.raises(ValueError):
        request(payload, event_id="synthetic", folder=tmp_path, guard=None, key=None, tags=TAGS)
