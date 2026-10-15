"""Contract checks for converting a production export without retaining provenance."""

import hashlib
import io
import json

import pytest

from demo_logic.dataset import canonical_bytes, prepare


def source_row(*, event_id: str, tags: list[str]) -> dict:
    """Build a synthetic production-v1 row with the requested ID and tags."""
    return {
        "external_id": event_id,
        "title": "Sichere Radwege",
        "normalized_title": "sichere radwege",
        "date": "2025-09-21",
        "start_time": "12:00",
        "weekday": 6,
        "time_bucket": "12:00",
        "venue_tokens": ["berlin"],
        "postcode": "10115",
        "lifecycle_status": "active",
        "tag_slugs": tags,
        "assignment_sources": {tag: "human" for tag in tags},
        "duplicate_key": "private-duplicate-key",
        "recurrence_seed": "series-123",
    }


def source_manifest(data: bytes, count: int) -> dict:
    """Build a synthetic manifest matching the supplied JSONL bytes and count."""
    return {
        "schema_version": 1,
        "taxonomy_version": "v1",
        "source_environment": "production",
        "exported_at": "2025-09-21T09:00:00Z",
        "git_revision": "a" * 40,
        "row_count": count,
        "content_sha256": hashlib.sha256(data).hexdigest(),
    }


def test_prepares_only_labeled_rows_and_removes_provenance() -> None:
    """Keep labeled records while removing private assignment metadata."""
    data = canonical_bytes(source_row(event_id="one", tags=["mobility"]))
    data += canonical_bytes(source_row(event_id="two", tags=[]))

    prepared, summary = prepare(
        io.BytesIO(data), source_manifest(data, 2), expected_source="production"
    )

    rows = [json.loads(line) for line in prepared.splitlines()]
    assert len(rows) == 1
    assert rows[0]["tag_slugs"] == ["mobility"]
    assert rows[0]["recurrence_key"] == "series-123"
    assert "assignment_sources" not in rows[0]
    assert "duplicate_key" not in rows[0]
    assert summary["row_count"] == 1
    assert summary["excluded_counts"] == {"untagged_demos": 1}
    assert summary["source_content_sha256"] == hashlib.sha256(data).hexdigest()


def test_rejects_export_with_wrong_hash() -> None:
    """Reject source bytes that do not match the export manifest."""
    data = canonical_bytes(source_row(event_id="one", tags=["mobility"]))
    manifest = source_manifest(data, 1)
    manifest["content_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="SHA-256"):
        prepare(io.BytesIO(data), manifest, expected_source="production")


def test_rejects_unexpected_fields() -> None:
    """Stop when a changed exporter introduces an unrecognized field."""
    row = source_row(event_id="one", tags=["mobility"])
    row["raw_json"] = {"private": True}
    data = canonical_bytes(row)

    with pytest.raises(ValueError, match="Unexpected export fields"):
        prepare(io.BytesIO(data), source_manifest(data, 1), expected_source="production")


def test_unicode_escapes_and_literal_characters_have_the_same_bytes() -> None:
    """Encode equivalent escaped and literal Unicode text identically."""
    escaped = json.loads(r'{"title":"\u00dcber \u00c4pfel (Du&#703;&#257;&#702;)"}')
    literal = {"title": "Über Äpfel (Du&#703;&#257;&#702;)"}

    assert canonical_bytes(escaped) == canonical_bytes(literal)
    assert json.loads(canonical_bytes(escaped)) == literal


def test_canonical_bytes_does_not_silently_normalize_or_replace_text() -> None:
    """Preserve valid text differences and reject malformed Unicode."""
    combining = {"title": "A\u0308pfel"}
    assert json.loads(canonical_bytes(combining)) == combining
    assert canonical_bytes(combining) != canonical_bytes({"title": "Äpfel"})

    with pytest.raises(ValueError, match="malformed Unicode"):
        canonical_bytes({"title": "\ud800"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", None),
        ("normalized_title", "  "),
        ("venue_tokens", [None]),
        ("recurrence_seed", ""),
        ("date", "20250921"),
        ("date", "2026-09-26"),
        ("weekday", 3),
        ("postcode", {"unexpected": "object"}),
        ("tag_slugs", [{}]),
    ],
)
def test_invalid_source_fields_fail_before_prepared_data_is_returned(
    field: str, value: object
) -> None:
    """Reject malformed input here instead of failing later during splitting."""
    row = source_row(event_id="one", tags=["mobility"])
    row[field] = value
    data = canonical_bytes(row)
    with pytest.raises((ValueError, TypeError)):
        prepare(io.BytesIO(data), source_manifest(data, 1), expected_source="production")


def test_source_manifest_must_be_an_object() -> None:
    with pytest.raises(TypeError, match="JSON object"):
        prepare(io.BytesIO(), [], expected_source="production")
