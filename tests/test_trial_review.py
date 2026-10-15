"""Review timing must exclude interruptions and preserve valid human answers."""

import pytest

from notebooks.tools.trial_review import ReviewClock, validate_review


def test_pauses_and_lookup_are_not_double_counted():
    now = [0.0]
    timer = ReviewClock(lambda: now[0])
    timer.resume()
    now[0] = 10
    timer.set_lookup(True)
    now[0] = 15
    timer.pause()
    now[0] = 100
    timer.resume()
    now[0] = 103
    timer.set_lookup(False)
    now[0] = 110
    timer.pause()
    assert timer.values() == (25, 8)
    now[0] = 200
    assert timer.values() == (25, 8)


def valid():
    return {
        "final_tags": ["housing"],
        "status": "resolved",
        "prior_exposure": "no",
        "context_needed": False,
        "active_seconds": 20,
        "context_seconds": 0,
        "notes": "",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"status": None},
        {"prior_exposure": None},
        {"context_needed": None},
        {"active_seconds": float("nan")},
        {"active_seconds": 0},
        {"context_seconds": 21},
        {"context_seconds": -1},
        {"final_tags": ["unknown"]},
        {"final_tags": ["housing", "housing"]},
        {"status": "unclear"},
        {"final_tags": []},
    ],
)
def test_incomplete_reviews_cannot_be_saved(change):
    with pytest.raises(ValueError):
        validate_review({**valid(), **change}, ["housing"])


def test_unclear_and_resolved_empty_answers_require_notes():
    for status in ["unclear", "resolved"]:
        validate_review(
            {
                **valid(),
                "status": status,
                "final_tags": [],
                "notes": "Title does not support a topic",
            },
            ["housing"],
        )
