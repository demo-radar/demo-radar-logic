"""Regression cases for saved benchmark corruption and stale review files."""

import csv
import hashlib
import json
from datetime import date

import pytest

from demo_logic.benchmark import load_benchmark, representative_selection
from demo_logic.splits import reserve_splits, save_private_split


@pytest.fixture
def bundle(tmp_path):
    rows = [
        {
            "external_id": f"synthetic-{i}",
            "title": f"Synthetic topic {i}",
            "normalized_title": f"synthetic topic {i}",
            "recurrence_key": f"series-{i}",
            "date": "2025-09-21",
            "start_time": "12:00",
            "postcode": "10115",
            "venue_tokens": ["synthetic"],
            "tag_slugs": ["mobility"],
        }
        for i in range(500)
    ]
    manifest, grouping = reserve_splits(rows, "synthetic-fingerprint")
    manifest["title_eligibility"] = {
        "minimum_words": 2,
        "source_row_count": 500,
        "eligible_row_count": 500,
        "excluded_count": 0,
    }
    paths = save_private_split(tmp_path, rows, manifest, grouping)
    return tmp_path, rows, manifest, paths


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        return reader.fieldnames, list(reader)


def write_csv(path, fields, records, delimiter=","):
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fields, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(records)


def fingerprint(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}


def test_valid_bundle_preserves_review_bytes_and_supports_semicolons(bundle):
    directory, rows, _, paths = bundle
    fields, pilot = read_csv(paths["rubric_pilot"])
    pilot[0]["reviewed_tags"] = "mobility"
    pilot[0]["notes"] = "Synthetic review; with a newline\nkept intact"
    write_csv(paths["rubric_pilot"], fields, pilot, delimiter=";")
    before = fingerprint(directory)
    saved = load_benchmark(directory, rows, "synthetic-fingerprint")
    assert len(saved.pilot_ids) == 40
    assert saved.pilot_tagged_count == 1
    assert fingerprint(directory) == before


@pytest.mark.parametrize(
    "corruption",
    [
        "no_final",
        "invalid_split",
        "duplicate_assignment",
        "row_count",
        "group_count",
        "tag_count",
        "cutoff",
        "cross_group",
        "eligibility",
        "snapshot_hash",
    ],
)
def test_manifest_corruption_is_rejected_without_overwriting(bundle, corruption):
    directory, rows, manifest, paths = bundle
    if corruption == "no_final":
        for item in manifest["assignments"]:
            if item["split"] == "final_test":
                item["split"] = "training"
    elif corruption == "invalid_split":
        manifest["assignments"][0]["split"] = "unrecognised"
    elif corruption == "duplicate_assignment":
        manifest["assignments"].append(manifest["assignments"][0].copy())
    elif corruption == "row_count":
        manifest["split_counts"]["final_test"] += 1
    elif corruption == "group_count":
        manifest["group_counts"]["training"] += 1
    elif corruption == "tag_count":
        manifest["tag_counts"]["training"]["mobility"] += 1
    elif corruption == "cutoff":
        manifest["latest_final_date"] = "2025-09-20"
    elif corruption == "cross_group":
        first = manifest["assignments"][0]
        other = next(x for x in manifest["assignments"] if x["split"] != first["split"])
        other["group_id"] = first["group_id"]
    elif corruption == "eligibility":
        manifest["title_eligibility"]["excluded_count"] += 1
    else:
        manifest["dataset_sha256"] = "wrong-snapshot"
    write_json(paths["manifest"], manifest)
    before = fingerprint(directory)
    with pytest.raises(ValueError, match="Preserve completed reviews"):
        load_benchmark(directory, rows, "synthetic-fingerprint")
    assert fingerprint(directory) == before


@pytest.mark.parametrize(
    "corruption",
    [
        "final_ids",
        "duplicate_final",
        "pilot_ids",
        "pilot_metadata_ids",
        "pilot_metadata_hash",
        "pilot_metadata_seed",
        "group_id",
        "group_membership",
    ],
)
def test_stale_review_artifacts_are_rejected(bundle, corruption):
    directory, rows, manifest, paths = bundle
    training_id = next(
        x["external_id"] for x in manifest["assignments"] if x["split"] == "training"
    )
    if corruption in {"final_ids", "duplicate_final", "pilot_ids"}:
        path = paths["rubric_pilot" if corruption == "pilot_ids" else "final_review"]
        fields, records = read_csv(path)
        records[0]["external_id"] = (
            records[1]["external_id"] if corruption == "duplicate_final" else training_id
        )
        write_csv(path, fields, records)
    elif corruption.startswith("pilot_metadata"):
        selection = json.loads(paths["pilot_selection"].read_text())
        if corruption == "pilot_metadata_ids":
            selection["records"][0]["external_id"] = training_id
        elif corruption == "pilot_metadata_hash":
            selection["dataset_sha256"] = "wrong-snapshot"
        else:
            selection["split_selection_seed"] += 1
        write_json(paths["pilot_selection"], selection)
    else:
        fields, _ = read_csv(paths["group_review"])
        group_id = manifest["assignments"][0]["group_id"]
        record = dict.fromkeys(fields, "")
        record.update(
            {
                "group_id": "unknown" if corruption == "group_id" else group_id,
                "row_count": "2",
                "first_date": "2025-09-21",
                "last_date": "2025-09-21",
            }
        )
        write_csv(paths["group_review"], fields, [record])
    before = fingerprint(directory)
    with pytest.raises(ValueError, match="Preserve completed reviews"):
        load_benchmark(directory, rows, "synthetic-fingerprint")
    assert fingerprint(directory) == before


def test_missing_bundle_explains_restore_instead_of_generating(tmp_path):
    with pytest.raises(FileNotFoundError, match="restore-the-private-benchmark"):
        load_benchmark(tmp_path, [], "synthetic-fingerprint")
    assert not list(tmp_path.iterdir())


def test_final_group_size_limit_is_enforced(bundle):
    directory, rows, manifest, paths = bundle
    final = [item for item in manifest["assignments"] if item["split"] == "final_test"]
    final[1]["group_id"] = final[0]["group_id"]
    manifest["group_counts"]["final_test"] -= 1
    manifest["max_final_group_size"] = 1
    write_json(paths["manifest"], manifest)
    with pytest.raises(ValueError, match="exceeds the saved size limit"):
        load_benchmark(directory, rows, "synthetic-fingerprint")


@pytest.mark.parametrize("value", ["not-json", '{"latest_final_date":'])
def test_malformed_json_has_recovery_guidance(bundle, value):
    directory, rows, _, paths = bundle
    paths["manifest"].write_text(value)
    with pytest.raises(ValueError, match="Preserve completed reviews"):
        load_benchmark(directory, rows, "synthetic-fingerprint")


@pytest.mark.parametrize("date_format", ["%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"])
def test_spreadsheet_group_dates_match_without_changing_files(bundle, date_format):
    directory, rows, manifest, paths = bundle
    fields, _ = read_csv(paths["group_review"])
    assignment = manifest["assignments"][0]
    event_date = next(
        row["date"] for row in rows if row["external_id"] == assignment["external_id"]
    )
    day = date.fromisoformat(event_date).strftime(date_format)
    record = dict.fromkeys(fields, "")
    record.update(
        {
            "group_id": assignment["group_id"],
            "row_count": "1",
            "first_date": day,
            "last_date": day,
        }
    )
    write_csv(paths["group_review"], fields, [record], delimiter=";")
    before = fingerprint(directory)
    assert load_benchmark(directory, rows, "synthetic-fingerprint").group_review_count == 1
    assert fingerprint(directory) == before


def test_preferred_title_is_a_display_label_not_model_input(bundle):
    directory, rows, manifest, paths = bundle
    fields, _ = read_csv(paths["group_review"])
    assignment = manifest["assignments"][0]
    original_title = next(
        row["title"] for row in rows if row["external_id"] == assignment["external_id"]
    )
    record = dict.fromkeys(fields + ["preferred_title"], "")
    record.update(
        {
            "group_id": assignment["group_id"],
            "row_count": "1",
            "first_date": "2025-09-21",
            "last_date": "2025-09-21",
            "preferred_title": "Readable event-type label",
        }
    )
    write_csv(paths["group_review"], fields + ["preferred_title"], [record])
    saved = load_benchmark(directory, rows, "synthetic-fingerprint")
    assert saved.group_review_count == 1
    assert saved.groups[assignment["group_id"]][0]["title"] == original_title


def test_representatives_ignore_labels_and_order_and_preserve_pilot():
    from types import SimpleNamespace

    # No label fields: selection must work without consulting any answers.
    groups = {
        "train": [
            {"external_id": "b", "date": "2026-01-01"},
            {"external_id": "a", "date": "2026-01-01"},
            {"external_id": "c", "date": "2026-02-01"},
        ],
        "val": [
            {"external_id": "d", "date": "2026-01-01"},
            {"external_id": "pilot", "date": "2026-02-01"},
        ],
        "final": [{"external_id": "f", "date": "2026-03-01"}],
    }
    assignments = [
        {"external_id": row["external_id"], "group_id": group, "split": split}
        for group, split in [("train", "training"), ("val", "validation"), ("final", "final_test")]
        for row in groups[group]
    ]
    bundle = SimpleNamespace(
        groups=groups,
        pilot_ids=["pilot"],
        manifest={"dataset_sha256": "source", "assignments": assignments},
    )
    result = representative_selection(bundle)
    assert {r["external_id"] for r in result["records"]} == {"a", "pilot", "f"}
    assert sorted(i for r in result["records"] for i in r["member_ids"]) == [
        "a",
        "b",
        "c",
        "d",
        "f",
        "pilot",
    ]
    for members in groups.values():
        members.reverse()
        for row in members:
            row["tag_slugs"] = ["a different answer"]
    assignments.reverse()
    assert representative_selection(bundle) == result
    bundle.pilot_ids = ["d"]
    assert representative_selection(bundle)["selection_sha256"] != result["selection_sha256"]
