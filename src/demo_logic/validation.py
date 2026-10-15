"""Shared checks for event fields used by preparation and snapshot loading."""

from datetime import date

from demo_logic.taxonomy import CURRENT_TAXONOMY, topic_tags

TOPIC_TAGS = topic_tags(CURRENT_TAXONOMY)


def validate_event_fields(row: dict, line_number: int) -> None:
    """Check fields in one full demonstration record.

    Grouping needs a non-empty normalized title and recurrence key. Date
    filtering and sorting need a real ``YYYY-MM-DD`` date and a weekday that
    matches it. CSV writing expects venue tokens to be a list of strings and
    postcode, start time, and time bucket to be strings or ``None``. The
    original title only needs to be text; an empty title can still be reviewed.
    This checks the record as a whole; topic tags are checked separately by
    ``validate_topic_tags``.

    For example, a row dated Wednesday, 23 September 2026 should contain
    ``"date": "2026-09-23"`` and ``"weekday": 2`` (Monday is 0). If the
    weekday is 3, validation reports a mismatch. A value such as
    ``"date": "20260923"`` is rejected because dates must use the standard
    year-month-day format.

    Args:
        row: One prepared event record.
        line_number: Its one-based line number. For example, pass ``8`` for the
            eighth JSONL row so any error points to line 8.

    Raises:
        TypeError: A field has an unexpected type.
        ValueError: A required value is empty or inconsistent with another
            field, such as a weekday that does not match the date.
    """
    for name in ("title", "normalized_title", "recurrence_key"):
        if not isinstance(row[name], str):
            raise TypeError(f"Invalid {name} at line {line_number}")
    for name in ("normalized_title", "recurrence_key"):
        if not row[name].strip():
            raise ValueError(f"Missing {name} at line {line_number}")
    for name in ("postcode", "start_time", "time_bucket"):
        if row[name] is not None and not isinstance(row[name], str):
            raise TypeError(f"Invalid {name} at line {line_number}")
    venues = row["venue_tokens"]
    if not isinstance(venues, list) or any(not isinstance(token, str) for token in venues):
        raise ValueError(f"Invalid venue_tokens at line {line_number}")
    event_date = validate_date(row["date"], f"date at line {line_number}")
    if type(row["weekday"]) is not int or row["weekday"] != event_date.weekday():
        raise ValueError(f"Weekday does not match date at line {line_number}")


def validate_date(value: str, description: str) -> date:
    """Parse a date written as ``YYYY-MM-DD``.

    Requiring one format keeps date comparisons in chronological order. For
    example, ``"2026-09-23"`` is accepted, but ``"20260923"`` is rejected,
    even though Python can interpret it as the same date.

    Args:
        value: Date text to check.
        description: Field name to include in the error message.

    Returns:
        The parsed calendar date.

    Raises:
        ValueError: The value is invalid or is not written as ``YYYY-MM-DD``.
    """
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {description}; expected YYYY-MM-DD") from exc
    if value != parsed.isoformat():
        raise ValueError(f"Invalid {description}; expected YYYY-MM-DD")
    return parsed


def validate_topic_tags(value: object, line_number: int, taxonomy_version: str = "v1") -> list[str]:
    """Check topic tags and return them sorted, without duplicates.

    Source rows are allowed to have no tags; later snapshot validation checks
    that prepared rows have at least one. For example, ``["mobility",
    "environment", "mobility"]`` becomes ``["environment", "mobility"]``.
    Unknown tags and values that are not strings are rejected.

    Args:
        value: The row's tag list. It may be empty for an untagged source row.
        line_number: Its one-based line number, included in error messages.
        taxonomy_version: Catalog to validate against. The default preserves
            callers reading the original v1 export; v2 callers must pass v2.

    Returns:
        The unique topic tags in alphabetical order.

    Raises:
        ValueError: The value is not a list of approved tags, or contains
            more than two different tags.
    """
    approved = topic_tags(taxonomy_version)
    if not isinstance(value, list) or any(
        not isinstance(tag, str) or tag not in approved for tag in value
    ):
        raise ValueError(f"Unknown topic tag at line {line_number}")
    tags = sorted(set(value))
    if len(tags) > 2:
        raise ValueError(f"More than two topic tags at line {line_number}")
    return tags
