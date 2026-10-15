"""Check the shared title eligibility rule used by both audit notebooks."""

import pytest

from demo_logic.notebook_support import tagging_eligible_rows, title_word_count


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("", 0),
        ("x", 1),
        ("Peace!", 1),
        ("Peace -", 1),
        ("  Peace\nnow  ", 2),
        ("Für Frieden", 2),
        ("Climate-action", 1),
        ("!!! ???", 0),
    ],
)
def test_title_word_count(title: str, expected: int) -> None:
    assert title_word_count(title) == expected


def test_filter_keeps_eligible_records_without_changing_source() -> None:
    rows = [{"title": "Peace"}, {"title": "Peace now"}, {"title": "Peace -"}]
    original = [row.copy() for row in rows]
    eligible = tagging_eligible_rows(rows)
    assert eligible == [rows[1]]
    assert rows == original
