"""Regression checks for grouping titles in a larger, repetitive corpus."""

import pytest

from demo_logic.splits import group_demonstrations


def grouping_row(number: int, title: str) -> dict:
    """Give each synthetic title an independent recurrence key."""
    return {
        "external_id": f"event-{number}",
        "normalized_title": title.casefold(),
        "recurrence_key": f"series-{number}",
    }


@pytest.mark.parametrize("variant", ["Sichere Radwege für Berlin!", "Sichere Radwege   für Berlin"])
def test_common_words_do_not_separate_equivalent_title_variants(variant: str) -> None:
    """Common-word filtering must not let cosmetic variants cross split groups."""
    rows = [grouping_row(index, f"Sichere Radwege für Berlin {index}") for index in range(101)]
    rows += [
        grouping_row(200, "Sichere Radwege für Berlin"),
        grouping_row(201, variant),
    ]

    grouping = group_demonstrations(rows)
    assert any(
        {row["external_id"] for row in members} == {"event-200", "event-201"}
        for members in grouping.groups.values()
    )
    assert len(grouping.groups) == 102
    assert group_demonstrations(list(reversed(rows))) == grouping


def test_matching_token_sets_still_require_character_similarity() -> None:
    """A reordered token set alone must not bypass the character threshold."""
    rows = [
        grouping_row(1, "Sichere Radwege für Berlin"),
        grouping_row(2, "Berlin für Radwege Sichere"),
    ]
    assert len(group_demonstrations(rows).groups) == 2


def test_shared_recurrence_key_keeps_different_titles_together() -> None:
    """Exporter recurrence evidence joins rows even without matching title words."""
    rows = [grouping_row(1, "Sichere Radwege"), grouping_row(2, "Verkehrswende jetzt")]
    rows[1]["recurrence_key"] = rows[0]["recurrence_key"]
    assert len(group_demonstrations(rows).groups) == 1
