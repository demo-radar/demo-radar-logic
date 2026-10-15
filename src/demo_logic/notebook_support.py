"""Private report saving and title eligibility shared by the data-audit notebooks."""

import json
import os
from pathlib import Path


def save_private_json(path: Path, report: dict) -> Path:
    """Save an audit report with owner-only access; refuse to replace changed content."""
    content = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(
                f"Report differs from existing file; keep it and use a new path: {path}"
            )
        return path
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as destination:
        destination.write(content)
    return path


def title_word_count(title: str) -> int:
    """Count whitespace-separated words containing at least one letter or digit.

    For example, ``'Peace now'`` has two words, ``'Peace!'`` has one, and
    ``'Peace -'`` has one. Hyphenated words count as one; extra spaces are ignored.
    """
    return sum(any(character.isalnum() for character in word) for word in title.split())


def tagging_eligible_rows(rows: list[dict]) -> list[dict]:
    """Keep records with at least two title words, without changing the input rows."""
    return [row for row in rows if title_word_count(row["title"]) >= 2]
