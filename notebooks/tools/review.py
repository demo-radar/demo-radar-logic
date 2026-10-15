"""Private, human-readable review exports from already saved model predictions."""

import os
from html import escape
from pathlib import Path

from .hashes import fingerprint


def write_nli_review(path: Path, report: dict, validation: list[dict]) -> Path:
    """Export check-set disagreements without changing labels or running inference.

    Args:
        path: New private Markdown file, normally under reports/semantic-review/.
        report: Notebook 06 report, including predictions and original input hashes.
        validation: Matching development representatives with titles and historical tags.

    All disagreements in the separate check subset are included in ID order.
    Cutoff-selection examples and final-test examples are excluded. Title hashes
    must match the saved predictions. Review decisions are left blank for the reviewer;
    existing files are never overwritten, including files with added review notes.
    """
    rows = {r["external_id"]: r for r in validation}
    check_ids = report["check_ids"]
    if len(rows) != len(validation) or len(set(check_ids)) != len(check_ids):
        raise ValueError("Review input contains duplicate event IDs")
    if not set(check_ids).issubset(rows) or set(check_ids) & set(report["threshold_selection_ids"]):
        raise ValueError("Review must use separate validation-check examples only")
    policy = next(p for p in report["policies"] if p["policy"] == "include_cutoff_ties")
    predictions = {p["external_id"]: p["predicted"] for p in policy["predictions"]}
    events = {e["external_id"]: e for e in report["events"]}
    tags = report["inference_settings"]["tags"]
    disagreements = []
    for event_id in sorted(check_ids):
        row = rows[event_id]
        event = events[event_id]
        if event["identity"]["title_sha256"] != fingerprint(row["title"]):
            raise ValueError(f"Title changed since inference: {event_id}")
        if set(row["tag_slugs"]) != set(predictions[event_id]):
            disagreements.append(event_id)
    lines = [
        "# NLI versus historical tags — private review",
        "",
        f"Report: `{report['run_id']}`. Policy: top two plus exact ties. Cutoff: {policy['threshold']}.",
        f"All **{len(disagreements)} disagreements out of {len(check_ids)} check examples** are below.",
        "These are development examples, not final-test examples. No cases were picked by topic or score.",
        "",
        "## How to review",
        "",
        "1. Read the original title and compare both tag lists with rubric-v1.",
        "2. Choose: historical tags supported / NLI tags supported / both need changes / unclear.",
        "3. Write your preferred tags and a short reason. Add a source URL only if you checked it.",
        "",
        "A disagreement does not prove the old data is corrupted or that NLI is wrong.",
        "Scores are not correctness probabilities. Neutral near 1 means the NLI model found little",
        "support or contradiction; the separate binary score can still be high.",
        "Leave uncertain cases unresolved. We will review decisions before changing any dataset.",
        "Because predictions are visible here, these answers are model-assisted development review,",
        "not independent final-test labels. This file must stay outside Git.",
        "",
    ]
    for number, event_id in enumerate(disagreements, 1):
        row, event = rows[event_id], events[event_id]
        historical, suggested = set(row["tag_slugs"]), set(predictions[event_id])
        lines += [
            f"## {number}. {escape(event_id)}",
            "",
            f"<pre>{escape(row['title'])}</pre>",
            "",
            f"- Historical tags: {escape('; '.join(sorted(historical)) or '(none)')}",
            f"- NLI suggestions: {escape('; '.join(predictions[event_id]) or '(no suggestion)')}",
            f"- Added by NLI: {escape('; '.join(sorted(suggested - historical)) or '(none)')}",
            f"- Historical tags missed by NLI: {escape('; '.join(sorted(historical - suggested)) or '(none)')}",
            "",
            "| Relevant tag | NLI score | Neutral output |",
            "|---|---:|---:|",
        ]
        for tag in sorted(historical | suggested):
            index = tags.index(tag)
            lines.append(
                f"| {escape(tag)} | {event['scores'][index]:.3f} | "
                f"{event['neutral_probabilities'][index]:.3f} |"
            )
        lines += ["", "**Decision:** ", "", "**Preferred tags:** ", "", "**Reason / source:** ", ""]
    content = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation protects the reviewer's notes on later notebook runs.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path
