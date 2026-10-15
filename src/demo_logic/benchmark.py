"""Read and validate the saved private benchmark without redrawing its split."""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from demo_logic.notebook_support import tagging_eligible_rows

FILES = {
    "manifest": "split-manifest.json",
    "group_review": "group-review.csv",
    "rubric_pilot": "rubric-pilot-queue.csv",
    "pilot_selection": "rubric-pilot-selection.json",
    "final_review": "final-review-queue.csv",
}
SPLITS = {"training", "validation", "final_test"}
SELECTION_VERSION = "event-type-representatives-v1"
RECOVERY = (
    " Preserve completed reviews. Restore the matching private benchmark bundle or "
    "reconcile its IDs and metadata; do not regenerate blank forms over it. "
    "See docs/data-preparation.md#restore-the-private-benchmark."
)


@dataclass(frozen=True)
class Benchmark:
    """Validated saved assignments and private review metadata for notebook display."""

    manifest: dict
    groups: dict[str, list[dict]]
    pilot_ids: list[str]
    paths: dict[str, Path]
    pilot_tagged_count: int
    group_review_count: int


def _require(condition: bool, message: str) -> None:
    """Stop with reconciliation guidance without printing private event content."""
    if not condition:
        raise ValueError(message + RECOVERY)


def _json(path: Path) -> dict:
    """Read a JSON object, identifying only the artifact name on malformed input."""
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.name} must contain a JSON object.")
    return value


def _csv(path: Path, required: set[str]) -> list[dict]:
    """Read comma or semicolon CSVs, preserving extra human review columns.

    Spreadsheet editors may change the delimiter or add a UTF-8 BOM. The known
    header names contain neither separator. Duplicate columns, truncated rows,
    and excess fields are rejected rather than silently losing review content.
    """
    with path.open(encoding="utf-8-sig", newline="") as source:
        header = source.readline()
        source.seek(0)
        delimiter = ";" if header.count(";") > header.count(",") else ","
        reader = csv.DictReader(source, delimiter=delimiter, strict=True)
        fields = reader.fieldnames or []
        _require(
            required.issubset(fields) and len(fields) == len(set(fields)),
            f"{path.name} has missing or duplicate columns.",
        )
        rows = list(reader)
    _require(
        all(None not in row and all(value is not None for value in row.values()) for row in rows),
        f"{path.name} has incomplete rows or excess fields.",
    )
    return rows


def _ids(records: list[dict], key: str, label: str) -> list[str]:
    """Extract unique nonempty identifiers without changing their source spelling."""
    _require(isinstance(records, list), f"{label} must be a list of records.")
    _require(all(isinstance(row, dict) for row in records), f"{label} has invalid records.")
    values = [row.get(key) for row in records]
    _require(
        all(isinstance(value, str) and bool(value.strip()) for value in values),
        f"{label} has missing identifiers.",
    )
    _require(len(values) == len(set(values)), f"{label} has duplicate identifiers.")
    return values


def load_benchmark(directory: Path, snapshot_rows: list[dict], dataset_sha256: str) -> Benchmark:
    """Load a complete benchmark bundle and verify it against a validated snapshot.

    Args:
        directory: Private folder containing the five files named in ``FILES``.
        snapshot_rows: Full prepared snapshot returned by ``load_snapshot``.
            The agreed two-word title rule is applied here before checking IDs.
        dataset_sha256: Fingerprint returned by the prepared snapshot loader.

    Returns:
        Saved groups, assignments, paths, and aggregate review counts. Grouping
        is recovered from the manifest, not recomputed with today's algorithm.

    Raises:
        FileNotFoundError: The bundle is incomplete; restore the matching files.
        ValueError: Assignments, summaries, selection policies, or review IDs
            disagree. No file is created, edited, or repaired by this function.

    Review text is retained but not judged: a nonempty tag field does not prove
    a correct label or complete human review. ``preferred_title`` is a display
    label for the event type, not a source title or model input. A frozen split
    also verifies the recorded membership and group-review decision fingerprints.
    """
    paths = {name: directory / filename for name, filename in FILES.items()}
    missing = [path.name for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing benchmark artifacts: " + ", ".join(missing) + RECOVERY)
    try:
        return _load(paths, snapshot_rows, dataset_sha256)
    except ValueError as error:
        if str(error).endswith(RECOVERY):
            raise
        raise ValueError("Malformed benchmark value." + RECOVERY) from error
    except (KeyError, TypeError, csv.Error, UnicodeError) as error:
        raise ValueError("Malformed benchmark artifact." + RECOVERY) from error


def _matches_review_date(value: str, expected: str) -> bool:
    """Accept ISO or German spreadsheet formatting of the expected snapshot date.

    Compare renderings of the known date instead of guessing a century from a
    two-digit year. This supports reviewed CSVs without rewriting their bytes.
    """
    day = date.fromisoformat(expected)
    return value.strip() in {expected, day.strftime("%d.%m.%Y"), day.strftime("%d.%m.%y")}


def _load(paths: dict[str, Path], snapshot_rows: list[dict], dataset_sha256: str) -> Benchmark:
    """Validate manifest membership first, then join each review artifact to it."""
    manifest = _json(paths["manifest"])
    _require(manifest.get("schema_version") == 1, "Unsupported split manifest schema.")
    _require(
        manifest.get("dataset_sha256") == dataset_sha256, "Split snapshot fingerprint differs."
    )
    rows = tagging_eligible_rows(snapshot_rows)
    by_id = {row["external_id"]: row for row in rows}
    assignments = manifest["assignments"]
    assignment_ids = _ids(assignments, "external_id", "Split assignments")
    _require(set(assignment_ids) == set(by_id), "Assignments differ from eligible snapshot IDs.")
    group_rows = defaultdict(list)
    group_splits = defaultdict(set)
    counts = Counter()
    tag_counts = defaultdict(Counter)
    by_assignment = {}
    for item in assignments:
        split, group_id = item["split"], item["group_id"]
        _require(split in SPLITS, "Assignment has an unsupported split name.")
        _require(isinstance(group_id, str) and bool(group_id.strip()), "Missing assignment group.")
        row = by_id[item["external_id"]]
        group_rows[group_id].append(row)
        group_splits[group_id].add(split)
        counts[split] += 1
        tag_counts[split].update(row["tag_slugs"])
        by_assignment[item["external_id"]] = item
    _require(
        all(len(parts) == 1 for parts in group_splits.values()), "A group crosses split boundaries."
    )
    _require(set(counts) == SPLITS, "Training, validation, and final test must all be nonempty.")
    group_counts = Counter(next(iter(parts)) for parts in group_splits.values())
    _require(
        dict(counts) == manifest["split_counts"], "Stored split counts disagree with assignments."
    )
    _require(
        dict(group_counts) == manifest["group_counts"],
        "Stored group counts disagree with assignments.",
    )
    _require(
        {split: dict(tags) for split, tags in tag_counts.items()} == manifest["tag_counts"],
        "Stored tag counts disagree with snapshot labels and assignments.",
    )
    target, max_group = manifest["final_target"], manifest["max_final_group_size"]
    _require(type(target) is int and target >= 100, "Invalid final-test target.")
    _require(type(max_group) is int and max_group >= 1, "Invalid final group-size limit.")
    _require(100 <= counts["final_test"] <= target, "Actual final-test size is outside its limits.")
    cutoff = date.fromisoformat(manifest["latest_final_date"])
    for group_id, members in group_rows.items():
        if group_splits[group_id] == {"final_test"}:
            _require(len(members) <= max_group, "Final-test group exceeds the saved size limit.")
            _require(
                all(date.fromisoformat(row["date"]) <= cutoff for row in members),
                "Final-test group exceeds the saved date cutoff.",
            )
    eligibility = manifest.get("title_eligibility", {})
    expected = {
        "minimum_words": 2,
        "source_row_count": len(snapshot_rows),
        "eligible_row_count": len(rows),
        "excluded_count": len(snapshot_rows) - len(rows),
    }
    _require(
        all(eligibility.get(key) == value for key, value in expected.items()),
        "Saved title eligibility differs from the current snapshot and two-word rule.",
    )

    review_fields = {"external_id", "reviewed_tags", "uncertainty", "source_links", "notes"}
    pilot = _csv(paths["rubric_pilot"], review_fields)
    pilot_ids = _ids(pilot, "external_id", "Pilot queue")
    _require(len(pilot_ids) == 40, "Pilot must contain 40 distinct records.")
    _require(
        all(by_assignment.get(event_id, {}).get("split") == "validation" for event_id in pilot_ids),
        "Pilot queue contains IDs outside validation.",
    )
    _require(
        len({by_assignment[event_id]["group_id"] for event_id in pilot_ids}) == 40,
        "Pilot must represent 40 different groups.",
    )
    selection = _json(paths["pilot_selection"])
    _require(selection.get("schema_version") == 1, "Unsupported pilot selection schema.")
    _require(
        selection.get("dataset_sha256") == dataset_sha256, "Pilot selection fingerprint differs."
    )
    _require(
        selection.get("split_selection_seed") == manifest["selection_seed"],
        "Pilot selection seed differs from the saved split.",
    )
    selected_ids = _ids(selection["records"], "external_id", "Pilot selection")
    _require(
        set(selected_ids) == set(pilot_ids), "Pilot selection IDs disagree with the review queue."
    )
    final_ids = _ids(
        _csv(paths["final_review"], review_fields), "external_id", "Final review queue"
    )
    expected_final = {item["external_id"] for item in assignments if item["split"] == "final_test"}
    _require(
        set(final_ids) == expected_final, "Final review queue differs from saved final-test IDs."
    )
    reviews = _csv(paths["group_review"], {"group_id", "row_count", "first_date", "last_date"})
    review_ids = _ids(reviews, "group_id", "Group review")
    _require(set(review_ids).issubset(group_rows), "Group review references unknown saved groups.")
    for review in reviews:
        members = group_rows[review["group_id"]]
        dates = [row["date"] for row in members]
        _require(
            review["row_count"] == str(len(members))
            and _matches_review_date(review["first_date"], min(dates))
            and _matches_review_date(review["last_date"], max(dates)),
            "Group review describes different group membership.",
        )
    if manifest.get("status") == "frozen":
        freeze = manifest.get("freeze", {})
        _require(freeze.get("version") == 1, "Missing or unsupported split freeze record.")
        _require(
            freeze.get("assignments_sha256") == assignment_fingerprint(assignments),
            "Frozen split membership changed; reconcile and version the split explicitly.",
        )
        _require(
            freeze.get("reviewed_group_count") == len(reviews)
            and freeze.get("decisions_sha256") == decision_fingerprint(reviews),
            "Frozen group decisions changed; reconcile and version the split explicitly.",
        )
    return Benchmark(
        manifest,
        dict(group_rows),
        pilot_ids,
        paths,
        sum(bool(row["reviewed_tags"].strip()) for row in pilot),
        len(reviews),
    )


def assignment_fingerprint(assignments: list[dict]) -> str:
    """Fingerprint event/group/split membership independently of JSON formatting.

    Display titles and later reference-label edits do not change membership.
    Sorting by event ID makes a harmless change of manifest row order acceptable.
    """
    records = sorted((item["external_id"], item["group_id"], item["split"]) for item in assignments)
    return hashlib.sha256(json.dumps(records, ensure_ascii=False).encode("utf-8")).hexdigest()


def representative_selection(benchmark: Benchmark) -> dict:
    """Select one original record per saved event group without reading its labels.

    Args:
        benchmark: A bundle already checked by ``load_benchmark``.

    Returns:
        A versioned selection manifest with every selected ID and all its member
        IDs. Original split assignments and source records remain unchanged.
        The earliest ISO date wins, with event ID breaking ties. For validation
        groups in the existing pilot, retain the preselected pilot ID instead.
        This exception preserves human work; pilot tags never enter selection.

    The chosen record supplies its original title and historical labels in
    development experiments. Do not union or vote across conflicting labels.
    Final labels are joined separately only for final evaluation. The digest
    identifies this policy, the source snapshot and exact selected membership.
    """
    assignments = {item["external_id"]: item for item in benchmark.manifest["assignments"]}
    pilot_ids = set(benchmark.pilot_ids)
    records = []
    for group_id, members in sorted(benchmark.groups.items()):
        pilot = [row for row in members if row["external_id"] in pilot_ids]
        _require(len(pilot) <= 1, "More than one pilot record belongs to a group.")
        chosen = pilot[0] if pilot else min(members, key=lambda r: (r["date"], r["external_id"]))
        item = assignments[chosen["external_id"]]
        _require(not pilot or item["split"] == "validation", "Pilot must stay in validation.")
        records.append(
            {
                "group_id": group_id,
                "split": item["split"],
                "external_id": chosen["external_id"],
                "member_ids": sorted(row["external_id"] for row in members),
                "reason": "existing_pilot" if pilot else "earliest_date_then_id",
            }
        )
    result = {
        "version": SELECTION_VERSION,
        "dataset_sha256": benchmark.manifest["dataset_sha256"],
        "assignments_sha256": assignment_fingerprint(benchmark.manifest["assignments"]),
        "split_counts": dict(sorted(Counter(item["split"] for item in records).items())),
        "records": records,
    }
    result["selection_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return result


def decision_fingerprint(reviews: list[dict]) -> str:
    """Validate keep-together decisions and fingerprint their event-type IDs.

    Only the agreed 'same event' decision is supported by this freeze workflow.
    A request to separate a group, a blank answer, or an unclear answer needs
    reconciliation before freezing. Human-readable titles remain editable.
    """
    _require(bool(reviews), "No group decisions are available to freeze.")
    _require(
        all(row.get("decision", "").strip().casefold() == "same event" for row in reviews),
        "Every group decision must say 'same event' before this split can be frozen.",
    )
    records = sorted((row["group_id"], "same event") for row in reviews)
    return hashlib.sha256(json.dumps(records).encode("utf-8")).hexdigest()
