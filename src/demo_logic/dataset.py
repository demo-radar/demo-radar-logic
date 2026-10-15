"""Convert production schema-v1/v2 exports into DemoLogic's private v2 schema.

Read JSONL from standard input so the richer production export does not need
to be stored locally. Never print individual records or assignment provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path
from typing import BinaryIO

from demo_logic.snapshot import PREPARED_FIELDS
from demo_logic.taxonomy import topic_tags
from demo_logic.validation import TOPIC_TAGS, validate_event_fields, validate_topic_tags

__all__ = ["TOPIC_TAGS", "canonical_bytes", "main", "prepare"]

SOURCE_FIELDS = frozenset(
    {
        "external_id",
        "title",
        "normalized_title",
        "date",
        "start_time",
        "weekday",
        "time_bucket",
        "venue_tokens",
        "postcode",
        "lifecycle_status",
        "tag_slugs",
        "assignment_sources",
        "duplicate_key",
        "recurrence_seed",
    }
)


def canonical_bytes(row: dict) -> bytes:
    """Encode one dataset row as deterministic UTF-8 JSONL.

    The same dictionary always produces the same bytes: keys are sorted,
    spacing is fixed, and the line ends with a newline. This function does not
    clean the text. JSON Unicode escapes have already been decoded by
    ``json.loads``; HTML entities, unusual spacing, and split words remain.

    Args:
        row: JSON-serializable fields for one source or prepared record.

    Returns:
        One UTF-8 JSON object followed by a newline.

    Raises:
        ValueError: A string contains malformed Unicode that cannot be
            encoded as UTF-8.
    """
    try:
        return (
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Dataset row contains malformed Unicode") from exc


def prepare(source: BinaryIO, source_manifest: dict, *, expected_source: str) -> tuple[bytes, dict]:
    """Convert and verify a Demo Radar export using its declared taxonomy.

    Read the source JSONL without changing its original text. Keep only
    active, dated demonstrations with approved topic tags, remove assignment
    provenance, and build a summary of exclusions and field quality. The
    source stream's row count and SHA-256 must match its manifest before this
    function returns data for the caller to save.

    Args:
        source: Binary stream of source JSONL, positioned at its beginning.
        source_manifest: Metadata and fingerprint produced with that stream
            by the Demo Radar exporter.
        expected_source: Required environment name, normally ``production``.

    Returns:
        A pair containing prepared schema-v2 JSONL bytes and a manifest with
        counts, source details, and the prepared-data fingerprint.

    Raises:
        ValueError: The export has the wrong schema, taxonomy, environment,
            record contents, row count, or SHA-256 fingerprint.
        TypeError: The manifest or a required text field has the wrong type.
    """
    if not isinstance(source_manifest, dict):
        raise TypeError("Source manifest must be a JSON object")
    source_schema = source_manifest.get("schema_version")
    if source_schema not in {1, 2}:
        raise ValueError("Expected production export schema v1 or v2")
    taxonomy_version = source_manifest.get("taxonomy_version")
    topic_tags(taxonomy_version)
    if source_manifest.get("source_environment") != expected_source:
        raise ValueError("Export came from an unexpected environment")

    source_hash = hashlib.sha256()
    prepared = io.BytesIO()
    exclusions: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    recurrence_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    source_rows = 0
    quality = Counter()

    for line_number, line in enumerate(source, start=1):
        source_hash.update(line)
        source_rows += 1
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}") from exc
        expected_fields = SOURCE_FIELDS if source_schema == 1 else PREPARED_FIELDS
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise ValueError(f"Unexpected export fields at line {line_number}")

        event_id = row["external_id"]
        if not isinstance(event_id, str) or not event_id or event_id in seen_ids:
            raise ValueError(f"Missing or repeated event ID at line {line_number}")
        seen_ids.add(event_id)

        if source_schema == 2 and (
            row["schema_version"] != 2 or row["taxonomy_version"] != taxonomy_version
        ):
            raise ValueError(f"Export row version mismatch at line {line_number}")
        if row.get("lifecycle_status", "active") == "deleted":
            exclusions["deleted_demos"] += 1
            continue
        if row.get("lifecycle_status", "active") != "active":
            raise ValueError(f"Unexpected lifecycle status at line {line_number}")
        if not row["date"]:
            exclusions["missing_date"] += 1
            continue

        tags = validate_topic_tags(row["tag_slugs"], line_number, taxonomy_version)
        if not tags:
            exclusions["untagged_demos"] += 1
            continue
        output_row = {
            "schema_version": 2,
            "taxonomy_version": taxonomy_version,
            "external_id": event_id,
            "title": row["title"],
            "normalized_title": row["normalized_title"],
            "date": row["date"],
            "start_time": row["start_time"],
            "weekday": row["weekday"],
            "time_bucket": row["time_bucket"],
            "venue_tokens": row["venue_tokens"],
            "postcode": row["postcode"],
            "tag_slugs": tags,
            "recurrence_key": row["recurrence_seed"]
            if source_schema == 1
            else row["recurrence_key"],
        }
        validate_event_fields(output_row, line_number)
        prepared.write(canonical_bytes(output_row))
        tag_counts.update(tags)
        recurrence_counts[output_row["recurrence_key"]] += 1
        if not row["title"].strip():
            quality["missing_title"] += 1
        if not row["postcode"]:
            quality["missing_postcode"] += 1
        if not row["start_time"]:
            quality["missing_start_time"] += 1
        if len(tags) == 2:
            quality["two_tag_rows"] += 1

    if source_rows != source_manifest.get("row_count"):
        raise ValueError("Source row count does not match its manifest")
    if source_hash.hexdigest() != source_manifest.get("content_sha256"):
        raise ValueError("Source SHA-256 does not match its manifest")

    data = prepared.getvalue()
    dates = [json.loads(line)["date"] for line in data.splitlines()]
    summary = {
        "schema_version": 2,
        "taxonomy_version": taxonomy_version,
        "source_environment": expected_source,
        "source_exported_at": source_manifest.get("exported_at"),
        "source_git_revision": source_manifest.get("git_revision"),
        "source_schema_version": source_schema,
        "label_review_status": source_manifest.get(
            "label_review_status", "historical_assignments_not_independently_reviewed"
        ),
        "source_row_count": source_rows,
        "source_content_sha256": source_hash.hexdigest(),
        "row_count": sum(recurrence_counts.values()),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "tag_counts": dict(sorted(tag_counts.items())),
        "excluded_counts": dict(sorted(exclusions.items())),
        "quality_counts": dict(sorted(quality.items())),
        "recurrence_group_count": len(recurrence_counts),
        "recurring_group_count": sum(count > 1 for count in recurrence_counts.values()),
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "transformation": f"production-v{source_schema}-to-demologic-v2",
    }
    return data, summary


def main() -> None:
    """Run the private export converter from the command line.

    Read source JSONL from standard input and the source manifest from the
    supplied path. Write the prepared dataset and manifest into ``--output-dir``
    only after ``prepare`` verifies the full source stream. Print a completion
    message; keep records and manifest metadata out of console logs.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-source", default="production")
    args = parser.parse_args()

    source_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    data, summary = prepare(sys.stdin.buffer, source_manifest, expected_source=args.expected_source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "dataset.jsonl").write_bytes(data)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("Prepared dataset and manifest saved.")


if __name__ == "__main__":
    main()
