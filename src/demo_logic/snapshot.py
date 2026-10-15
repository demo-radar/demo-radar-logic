"""Load and verify the private prepared dataset before analysis or splitting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from demo_logic.taxonomy import topic_tags
from demo_logic.validation import validate_event_fields, validate_topic_tags

PREPARED_FIELDS = frozenset(
    {
        "schema_version",
        "taxonomy_version",
        "external_id",
        "title",
        "normalized_title",
        "date",
        "start_time",
        "weekday",
        "time_bucket",
        "venue_tokens",
        "postcode",
        "tag_slugs",
        "recurrence_key",
    }
)


def load_snapshot(dataset_path: Path, manifest_path: Path) -> tuple[list[dict], dict]:
    """Read a prepared snapshot only when its manifest and rows agree.

    Args:
        dataset_path: Private schema-v2 JSONL produced by the converter.
        manifest_path: Its paired private metadata and SHA-256 fingerprint.

    Returns:
        Validated rows in file order and the original manifest.

    Raises:
        FileNotFoundError: Preparation has not created both input files.
        ValueError: The hash, row count, schema, IDs, dates, or tags are invalid.
        TypeError: The manifest or a required text field has the wrong type.
    """
    if not dataset_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(
            "Private dataset or manifest is missing; follow docs/data-preparation.md first"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise TypeError("Prepared manifest must be a JSON object")
    if manifest.get("schema_version") != 2:
        raise ValueError("Expected prepared schema v2")
    taxonomy_version = manifest.get("taxonomy_version")
    topic_tags(taxonomy_version)

    content = dataset_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != manifest.get("content_sha256"):
        raise ValueError("Prepared dataset SHA-256 does not match its manifest")

    rows: list[dict] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(content.splitlines(), start=1):
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid prepared JSONL at line {line_number}") from exc
        if not isinstance(row, dict) or set(row) != PREPARED_FIELDS:
            raise ValueError(f"Unexpected prepared fields at line {line_number}")
        if row["schema_version"] != 2 or row["taxonomy_version"] != taxonomy_version:
            raise ValueError(f"Unexpected row schema at line {line_number}")
        event_id = row["external_id"]
        if not isinstance(event_id, str) or not event_id or event_id in seen_ids:
            raise ValueError(f"Missing or repeated event ID at line {line_number}")
        seen_ids.add(event_id)
        validate_event_fields(row, line_number)
        tags = validate_topic_tags(row["tag_slugs"], line_number, taxonomy_version)
        if not tags or len(tags) != len(row["tag_slugs"]):
            raise ValueError(f"Invalid topic tags at line {line_number}")
        rows.append(row)

    if len(rows) != manifest.get("row_count"):
        raise ValueError("Prepared row count does not match its manifest")
    return rows, manifest
