"""Checks for private snapshot validation and leakage-controlled split artifacts."""

import csv
import hashlib
import io
import json
import stat
from datetime import date
from pathlib import Path

import pytest

from demo_logic.dataset import canonical_bytes
from demo_logic.snapshot import load_snapshot
from demo_logic.splits import (
    _csv_bytes,
    _group_review_bytes,
    choose_pilot_ids,
    group_demonstrations,
    reserve_splits,
    save_private_split,
)


def example_row(number: int, *, title: str | None = None, event_date: str = "2026-09-23") -> dict:
    """Build a synthetic prepared row with the expected schema."""
    return {
        "schema_version": 2,
        "taxonomy_version": "v1",
        "external_id": f"event-{number:04d}",
        "title": title or f"Synthetic event number {number}",
        "normalized_title": (title or f"Synthetic event number {number}").casefold(),
        "date": event_date,
        "start_time": "12:00",
        "weekday": date.fromisoformat(event_date).weekday(),
        "time_bucket": "12:00",
        "venue_tokens": ["berlin"],
        "postcode": "10115",
        "tag_slugs": ["mobility" if number % 2 else "environment"],
        "recurrence_key": f"series-{number}",
    }


def write_snapshot(directory: Path, rows: list[dict]) -> tuple[Path, Path]:
    """Write synthetic JSONL and a matching manifest for a loader test."""
    dataset = directory / "dataset.jsonl"
    manifest = directory / "manifest.json"
    content = b"".join(canonical_bytes(row) for row in rows)
    dataset.write_bytes(content)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "taxonomy_version": "v1",
                "row_count": len(rows),
                "content_sha256": hashlib.sha256(content).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return dataset, manifest


def test_snapshot_rejects_changed_bytes_and_repeated_ids(tmp_path: Path) -> None:
    """A snapshot cannot be analyzed after its content or IDs change."""
    dataset, manifest = write_snapshot(tmp_path, [example_row(1)])
    rows, metadata = load_snapshot(dataset, manifest)
    assert len(rows) == metadata["row_count"] == 1

    dataset.write_bytes(dataset.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256"):
        load_snapshot(dataset, manifest)

    dataset, manifest = write_snapshot(tmp_path, [example_row(1), example_row(1)])
    with pytest.raises(ValueError, match="repeated event ID"):
        load_snapshot(dataset, manifest)


def test_grouping_keeps_exact_and_strong_title_variants_together() -> None:
    """The same event title cannot leak through a changed recurrence key."""
    rows = [
        example_row(1, title="Sichere Radwege für Berlin"),
        example_row(2, title="Sichere Radwege für Berlin"),
        example_row(3, title="Sichere Radwege für Berlin!"),
        example_row(4, title="Bezahlbare Wohnungen jetzt"),
        example_row(5, title=" Bezahlbare Wohnungen jetzt"),
        example_row(6, title="Sichere Radwege   für Berlin"),
    ]
    grouping = group_demonstrations(rows)
    grouped_ids = [{row["external_id"] for row in members} for members in grouping.groups.values()]
    assert {"event-0001", "event-0002", "event-0003", "event-0006"} in grouped_ids
    assert len(grouping.similar_title_pairs) == 4
    assert len(grouping.groups) == 2


def test_grouping_does_not_merge_different_people_by_age() -> None:
    """Keep events about people of different ages in separate groups, even when their titles are similar."""
    rows = [
        example_row(1, title="Mahnwache für einen 35 jährigen Fußgänger"),
        example_row(2, title="Mahnwache für einen 71 jährigen Fußgänger"),
    ]
    grouping = group_demonstrations(rows)
    assert len(grouping.groups) == 2
    assert grouping.similar_title_pairs == ()


def test_split_is_stable_and_review_queues_do_not_expose_tags(tmp_path: Path) -> None:
    """Keep related events together when splitting the dataset.

    A group contains events with matching or very similar titles, or a shared
    recurrence key. All events in a group must go into the same split.

    This test checks that splits are repeatable and exclude far-future events from final
    testing. The 40-event review pilot must use distinct validation groups.
    Review forms must hide existing tags, have private file permissions, and
    refuse to overwrite human edits.

    For a real run, inspect data/dataset.jsonl and data/manifest.json; the
    snapshot hash is manifest.json's content_sha256. Split assignments and
    that same hash (as dataset_sha256) are in data/split-manifest.json.
    These private files are ignored by Git, so a fresh clone needs its own
    snapshot and split files. This test writes its files to tmp_path instead.
    """
    rows = [example_row(index) for index in range(500)]
    rows[1]["title"] = rows[0]["title"]
    rows[1]["normalized_title"] = rows[0]["normalized_title"]
    rows[-1] = example_row(499, title="Future series", event_date="2034-08-17")
    rows[-1]["weekday"] = 3
    first, grouping = reserve_splits(rows, "a" * 64)
    second, _ = reserve_splits(rows, "a" * 64)
    assert first == second
    assert first["split_counts"]["final_test"] == 150
    assert sum(first["split_counts"].values()) == len(rows)

    by_group: dict[str, set[str]] = {}
    for assignment in first["assignments"]:
        by_group.setdefault(assignment["group_id"], set()).add(assignment["split"])
    assert all(len(splits) == 1 for splits in by_group.values())
    assignments = {item["external_id"]: item["split"] for item in first["assignments"]}
    assert assignments["event-0499"] != "final_test"

    paths = save_private_split(tmp_path, rows, first, grouping)
    with paths["rubric_pilot"].open(encoding="utf-8-sig", newline="") as source:
        pilot_ids = {row["external_id"] for row in csv.DictReader(source)}
    assert len(pilot_ids) == 40
    assert all(assignments[event_id] == "validation" for event_id in pilot_ids)
    group_by_id = {item["external_id"]: item["group_id"] for item in first["assignments"]}
    assert len({group_by_id[event_id] for event_id in pilot_ids}) == 40
    assert "tag_slugs" not in paths["final_review"].read_text(encoding="utf-8-sig")
    assert "tag_slugs" not in paths["rubric_pilot"].read_text(encoding="utf-8-sig")
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in paths.values())

    paths["rubric_pilot"].write_text("human edits", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        save_private_split(tmp_path, rows, first, grouping)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", None),
        ("normalized_title", ""),
        ("venue_tokens", [42]),
        ("recurrence_key", "  "),
        ("date", "20250921"),
        ("weekday", 3),
        ("start_time", []),
        ("tag_slugs", [{}]),
        ("tag_slugs", ["mobility", "mobility"]),
    ],
)
def test_snapshot_rejects_invalid_fields_with_matching_hash(
    tmp_path: Path, field: str, value: object
) -> None:
    """A correct hash must not let malformed fields reach the review writer."""
    row = example_row(1)
    row[field] = value
    dataset, manifest = write_snapshot(tmp_path, [row])
    with pytest.raises((ValueError, TypeError)):
        load_snapshot(dataset, manifest)


def test_snapshot_manifest_must_be_an_object(tmp_path: Path) -> None:
    dataset, manifest = write_snapshot(tmp_path, [example_row(1)])
    manifest.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="JSON object"):
        load_snapshot(dataset, manifest)


@pytest.mark.parametrize("size", [-1, 0, 1.5, True])
def test_pilot_rejects_invalid_sizes(size: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        choose_pilot_ids([], {}, size=size)


def test_pilot_requires_enough_validation_groups() -> None:
    with pytest.raises(ValueError, match="too few independent groups"):
        choose_pilot_ids([], {"assignments": [], "selection_seed": 1})


def test_pilot_targeted_slot_prefers_health_then_two_tags() -> None:
    """After the random portion, prioritize overlap cases from unused groups."""
    rows = [example_row(index) for index in range(8)]
    manifest = {
        "selection_seed": 1,
        "assignments": [
            {"external_id": row["external_id"], "group_id": str(index), "split": "validation"}
            for index, row in enumerate(rows)
        ],
    }
    random_ids = choose_pilot_ids(rows, manifest, size=4)[:3]
    candidates = [row for row in rows if row["external_id"] not in random_ids]
    candidates[0]["tag_slugs"] = ["work", "social-issues"]
    assert choose_pilot_ids(rows, manifest, size=4)[-1] == candidates[0]["external_id"]
    candidates[1]["normalized_title"] = "mehr personal in der klinik"
    selected = choose_pilot_ids(rows, manifest, size=4)
    assert selected[:3] == random_ids
    assert selected[-1] == candidates[1]["external_id"]


def test_large_groups_stay_out_of_final_test_and_order_does_not_change_splits() -> None:
    rows = [example_row(index) for index in range(500)]
    for row in rows[:11]:
        row["recurrence_key"] = "large-series"
    manifest, _ = reserve_splits(rows, "a" * 64)
    shuffled, _ = reserve_splits(list(reversed(rows)), "a" * 64)
    assert manifest == shuffled
    assignments = {item["external_id"]: item["split"] for item in manifest["assignments"]}
    assert all(assignments[row["external_id"]] != "final_test" for row in rows[:11])


@pytest.mark.parametrize(
    "settings",
    [
        {"final_target": 99},
        {"final_target": 150.5},
        {"validation_fraction": 0},
        {"max_final_group_size": 0},
        {"latest_final_date": "20271231"},
    ],
)
def test_invalid_split_settings_are_rejected(settings: dict) -> None:
    with pytest.raises((ValueError, TypeError)):
        reserve_splits([], "a" * 64, **settings)


def test_split_rejects_too_few_test_events() -> None:
    with pytest.raises(ValueError, match="Fewer than 100"):
        reserve_splits([example_row(index) for index in range(99)], "a" * 64)


def test_review_csv_preserves_quoted_text_and_escapes_formula_fields() -> None:
    row = example_row(1, title='A title, with "quotes"\nand a second line')
    row.update(external_id="=1+1", postcode="+123", venue_tokens=["@venue"])
    content = _csv_bytes([row]).decode("utf-8-sig")
    reviewed = next(csv.DictReader(io.StringIO(content)))
    assert reviewed["title"] == row["title"]
    assert reviewed["external_id"] == "'=1+1"
    assert reviewed["postcode"] == "'+123"
    assert reviewed["venue_tokens"] == "'@venue"
    assert reviewed["reviewed_tags"] == ""
    assert "tag_slugs" not in reviewed


def test_formula_titles_are_escaped_in_both_review_formats() -> None:
    row = example_row(1, title="=1+1", event_date="2034-08-17")
    final_form = list(csv.DictReader(io.StringIO(_csv_bytes([row]).decode("utf-8-sig"))))
    groups = group_demonstrations([row])
    group_form = list(
        csv.DictReader(io.StringIO(_group_review_bytes(groups, "2027-12-31").decode("utf-8-sig")))
    )
    assert final_form[0]["title"] == "'=1+1"
    assert group_form[0]["title_variants"] == "'=1+1"


@pytest.mark.parametrize("cutoff", ["2026-09-24", "2028-03-10"])
def test_group_review_uses_candidate_cutoff(cutoff: str) -> None:
    """Dates on the cutoff are allowed; a later edition flags the whole group."""
    from datetime import timedelta

    following_day = (date.fromisoformat(cutoff) + timedelta(days=1)).isoformat()
    rows = [example_row(1, event_date=cutoff), example_row(2, event_date=following_day)]
    rows[1]["recurrence_key"] = rows[0]["recurrence_key"]
    groups = group_demonstrations(rows)

    def reasons_for(saved_cutoff: str) -> set[str]:
        content = _group_review_bytes(groups, saved_cutoff).decode("utf-8-sig")
        return {
            reason
            for record in csv.DictReader(io.StringIO(content))
            for reason in record["reason"].split(";")
        }

    assert "after_final_test_cutoff" in reasons_for(cutoff)
    assert "after_final_test_cutoff" not in reasons_for(following_day)
