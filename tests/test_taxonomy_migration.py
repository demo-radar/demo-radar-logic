"""A migration must preserve reviewed records and the original evaluation split."""

import hashlib
import io
import json

import pytest

from demo_logic.benchmark import load_benchmark
from demo_logic.dataset import canonical_bytes, prepare
from demo_logic.migrate_taxonomy import migrate
from demo_logic.snapshot import load_snapshot
from demo_logic.splits import reserve_splits, save_private_split
from demo_logic.validation import validate_topic_tags


def make_bundle(path):
    """Create synthetic source files with enough independent final-test groups."""
    path.mkdir()
    rows = [
        {
            "schema_version": 2,
            "taxonomy_version": "v1",
            "external_id": f"synthetic-{i}",
            "title": f"Synthetic topic {i}",
            "normalized_title": f"synthetic topic {i}",
            "recurrence_key": f"series-{i}",
            "date": "2025-09-21",
            "start_time": "12:00",
            "weekday": 6,
            "time_bucket": "12:00",
            "postcode": "10115",
            "venue_tokens": [],
            "tag_slugs": ["conflict", "human-rights"] if i % 2 else ["politics"],
        }
        for i in range(500)
    ]
    data = b"".join(canonical_bytes(row) for row in rows)
    fingerprint = hashlib.sha256(data).hexdigest()
    (path / "dataset.jsonl").write_bytes(data)
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "taxonomy_version": "v1",
                "row_count": len(rows),
                "content_sha256": fingerprint,
            }
        )
    )
    split, groups = reserve_splits(rows, fingerprint)
    split["title_eligibility"] = {
        "minimum_words": 2,
        "source_row_count": 500,
        "eligible_row_count": 500,
        "excluded_count": 0,
    }
    save_private_split(path / "benchmark", rows, split, groups)
    return rows, split


def test_separate_copy_preserves_source_features_and_assignments(tmp_path):
    source, output = tmp_path / "source", tmp_path / "v2"
    old_rows, old_split = make_bundle(source)
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    report = migrate(source, output)
    assert not output.exists()
    assert report["renamed_assignments"] == 250
    migrate(source, output, write=True)
    rows, manifest = load_snapshot(output / "dataset.jsonl", output / "manifest.json")
    bundle = load_benchmark(output / "benchmark", rows, manifest["content_sha256"])
    assert bundle.manifest["assignments"] == old_split["assignments"]
    for old, new in zip(old_rows, rows, strict=True):
        assert {k: v for k, v in old.items() if k not in {"taxonomy_version", "tag_slugs"}} == {
            k: v for k, v in new.items() if k not in {"taxonomy_version", "tag_slugs"}
        }
    assert rows[0]["tag_slugs"] == ["politics"]
    assert rows[1]["tag_slugs"] == ["human-rights", "international-politics"]
    assert before == {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }
    with pytest.raises(ValueError, match="new destination"):
        migrate(source, output, write=True)


def test_versions_cannot_silently_mix():
    assert validate_topic_tags(["conflict"], 1, "v1") == ["conflict"]
    assert validate_topic_tags(["international-politics"], 1, "v2") == ["international-politics"]
    with pytest.raises(ValueError, match="Unknown topic tag"):
        validate_topic_tags(["conflict"], 1, "v2")
    with pytest.raises(ValueError, match="Unknown topic tag"):
        validate_topic_tags(["international-politics"], 1, "v1")


@pytest.mark.parametrize("source_schema", [1, 2])
def test_source_export_with_new_taxonomy_is_accepted(tmp_path, source_schema):
    old_rows, _ = make_bundle(tmp_path / "source")
    row = {**old_rows[1], "taxonomy_version": "v2", "tag_slugs": ["international-politics"]}
    if source_schema == 1:
        row.pop("schema_version")
        row.pop("taxonomy_version")
        row["recurrence_seed"] = row.pop("recurrence_key")
        row.update(lifecycle_status="active", assignment_sources={}, duplicate_key="synthetic")
    data = canonical_bytes(row)
    source_manifest = {
        "schema_version": source_schema,
        "taxonomy_version": "v2",
        "source_environment": "production",
        "row_count": 1,
        "content_sha256": hashlib.sha256(data).hexdigest(),
    }
    result, manifest = prepare(io.BytesIO(data), source_manifest, expected_source="production")
    assert json.loads(result)["tag_slugs"] == ["international-politics"]
    assert manifest["taxonomy_version"] == "v2"


def test_review_translation_preserves_notes_and_three_tag_choices(tmp_path):
    import csv

    from demo_logic.migrate_taxonomy import _review_bytes

    path = tmp_path / "review.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["reviewed_tags", "uncertainty", "notes"])
        writer.writeheader()
        writer.writerow(
            {
                "reviewed_tags": "conflict, human-rights, politics",
                "uncertainty": "conflict: Low (5%) | politics: Low (10%)",
                "notes": "Original conflict wording; keep this",
            }
        )
    result = next(csv.DictReader(io.StringIO(_review_bytes(path).decode("utf-8-sig"))))
    assert result["reviewed_tags"] == "international-politics, human-rights, politics"
    assert result["uncertainty"] == "international-politics: Low (5%) | politics: Low (10%)"
    assert result["notes"] == "Original conflict wording; keep this"
