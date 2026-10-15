"""Group recurring demonstrations and reserve private benchmark records."""

from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from demo_logic.validation import validate_date

HEALTH_PATTERN = re.compile(r"gesundheit|pflege|klinik|krankenhaus|medizin|care", re.IGNORECASE)


@dataclass(frozen=True)
class Grouping:
    """Rows grouped by event title, recurrence key, and strong title variants."""

    groups: dict[str, list[dict]]
    titles: dict[str, list[str]]
    similar_title_pairs: tuple[tuple[str, str], ...]


def _rank(seed: int, purpose: str, value: str) -> str:
    """Give a group a stable pseudorandom rank without depending on row order."""
    return hashlib.sha256(f"{seed}\0{purpose}\0{value}".encode()).hexdigest()


def _title_pair_candidates(tokens: dict[str, set[str]]) -> list[tuple[str, str]]:
    """Find title pairs worth checking for similarity.

    ``tokens`` maps each normalized title to its set of words. For example,
    this input:

    ``{"sichere radwege für berlin": {"sichere", "radwege", "für", "berlin"},``
    `` "sichere radwege für berlin!": {"sichere", "radwege", "für", "berlin"}}``

    returns ``(("sichere radwege für berlin", "sichere radwege für berlin!"),)``.
    A later check decides whether they are similar enough to merge.

    Titles with different word sets can also be candidates if they share two
    words that each appear in no more than 100 titles. For example, if
    ``"sichere radwege für berlin"`` and
    ``"sichere radwege jetzt berlin"`` are the only titles containing
    ``"sichere"`` and ``"radwege"``, the pair is returned for a later check.
    Very common words appearing in more than 100 titles are skipped to limit
    comparisons. Matching word sets are still compared, even when their words
    are common, so punctuation or spacing variants remain candidates.

    Args:
        tokens: A dictionary such as ``{"title one": {"title", "one"}}``.

    Returns:
        Candidate title pairs in sorted order. A pair is only a possible match;
        ``_strong_title_match`` makes the final decision.

    Raises:
        No exception for valid input. The input must map strings to sets of
        strings.
    """
    token_index: dict[str, list[str]] = defaultdict(list)
    same_tokens: dict[frozenset[str], list[str]] = defaultdict(list)
    for title in sorted(tokens):
        informative = {token for token in tokens[title] if len(token) >= 4}
        for token in informative:
            token_index[token].append(title)
        if len(informative) >= 2:
            same_tokens[frozenset(tokens[title])].append(title)

    shared_tokens: Counter[tuple[str, str]] = Counter()
    for candidates in token_index.values():
        if len(candidates) <= 100:
            shared_tokens.update(combinations(candidates, 2))
    pairs = {pair for pair, count in shared_tokens.items() if count >= 2}
    for candidates in same_tokens.values():
        pairs.update(combinations(candidates, 2))
    return sorted(pairs)


def _strong_title_match(first: str, second: str, tokens: dict[str, set[str]]) -> bool:
    """Check textual similarity while keeping different numeric details apart."""
    same_numbers = set(re.findall(r"\d+", first)) == set(re.findall(r"\d+", second))
    overlap = len(tokens[first] & tokens[second]) / len(tokens[first] | tokens[second])
    return (
        same_numbers
        and overlap >= 0.8
        and difflib.SequenceMatcher(None, first, second).ratio() >= 0.92
    )


def group_demonstrations(rows: list[dict]) -> Grouping:
    """Keep likely editions of the same demonstration in one split group.

    Exact normalized titles and shared exporter recurrence keys always merge.
    Distinct titles merge only when they share at least two informative tokens,
    have token overlap of at least 0.8, and have character similarity of at
    least 0.92. Number tokens must also agree: changing a person's age can
    describe a different event despite nearly identical text. This errs
    toward keeping possible variants together; the private group-review file
    exposes such merges for inspection.

    For example, "Sichere Radwege für Berlin" and "Sichere Radwege für
    Berlin!" go into one group even if their recurrence keys differ. The
    group is assigned to one split, so one event cannot appear in training
    while the other appears in final testing. By contrast, "Mahnwache für
    einen 35 jährigen Fußgänger" and "Mahnwache für einen 71 jährigen
    Fußgänger" stay in separate groups when their recurrence keys differ.

    Args:
        rows: Validated prepared rows from ``load_snapshot``.

    Returns:
        Grouped rows, each group's original title variants, and the pairs
        merged by the similarity rule.
    """
    by_title: dict[str, list[dict]] = defaultdict(list)
    by_recurrence: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        title = row["normalized_title"]
        by_title[title].append(row)
        by_recurrence[row["recurrence_key"]].add(title)

    titles = sorted(by_title)
    parents = {title: title for title in titles}

    def find(title: str) -> str:
        while parents[title] != title:
            parents[title] = parents[parents[title]]
            title = parents[title]
        return title

    def merge(first: str, second: str) -> None:
        left, right = find(first), find(second)
        if left != right:
            parents[max(left, right)] = min(left, right)

    for recurrence_titles in by_recurrence.values():
        ordered = sorted(recurrence_titles)
        for title in ordered[1:]:
            merge(ordered[0], title)

    tokens = {title: set(re.findall(r"\w+", title.casefold())) for title in titles}
    similar_pairs: list[tuple[str, str]] = []
    for first, second in _title_pair_candidates(tokens):
        if _strong_title_match(first, second, tokens):
            merge(first, second)
            similar_pairs.append((first, second))

    grouped_titles: dict[str, list[str]] = defaultdict(list)
    for title in titles:
        grouped_titles[find(title)].append(title)

    groups: dict[str, list[dict]] = {}
    title_variants: dict[str, list[str]] = {}
    for root, variants in sorted(grouped_titles.items()):
        group_id = hashlib.sha256(root.encode("utf-8")).hexdigest()[:20]
        if group_id in groups:
            raise ValueError("Title-group hash collision")
        groups[group_id] = sorted(
            (row for title in variants for row in by_title[title]),
            key=lambda row: row["external_id"],
        )
        title_variants[group_id] = sorted(variants)

    return Grouping(groups, title_variants, tuple(similar_pairs))


def _select_groups(
    groups: dict[str, list[dict]], candidates: list[str], target: int, seed: int, purpose: str
) -> tuple[set[str], int]:
    """Select whole groups in a repeatable order, without exceeding the row target."""
    selected: set[str] = set()
    row_count = 0
    for group_id in sorted(candidates, key=lambda item: _rank(seed, purpose, item)):
        group_size = len(groups[group_id])
        if row_count + group_size <= target:
            selected.add(group_id)
            row_count += group_size
        if row_count == target:
            break
    return selected, row_count


def _split_assignments(
    grouping: Grouping, final_groups: set[str], validation_groups: set[str], row_count: int
) -> dict:
    """Record each event's split and count rows, groups, and historical tags."""
    assignments = []
    split_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    tag_counts: dict[str, Counter[str]] = defaultdict(Counter)
    split_by_group = dict.fromkeys(grouping.groups, "training")
    split_by_group.update(dict.fromkeys(validation_groups, "validation"))
    split_by_group.update(dict.fromkeys(final_groups, "final_test"))
    for group_id, members in grouping.groups.items():
        split = split_by_group[group_id]
        group_counts[split] += 1
        for row in members:
            assignments.append(
                {"external_id": row["external_id"], "split": split, "group_id": group_id}
            )
            split_counts[split] += 1
            tag_counts[split].update(row["tag_slugs"])
    assignments.sort(key=lambda item: item["external_id"])
    if len(assignments) != row_count or len({a["external_id"] for a in assignments}) != row_count:
        raise ValueError("Split assignments are incomplete or repeated")
    return {
        "split_counts": dict(sorted(split_counts.items())),
        "group_counts": dict(sorted(group_counts.items())),
        "tag_counts": {
            split: dict(sorted(counts.items())) for split, counts in sorted(tag_counts.items())
        },
        "assignments": assignments,
    }


def reserve_splits(
    rows: list[dict],
    dataset_sha256: str,
    *,
    seed: int = 20250921,
    final_target: int = 150,
    validation_fraction: float = 0.2,
    max_final_group_size: int = 10,
    latest_final_date: str = "2027-12-31",
) -> tuple[dict, Grouping]:
    """Assign each group of related events to one dataset split.

    First, group events that may be editions of the same demonstration.
    Choose whole groups for ``final_test``, then choose whole groups from
    those left for ``validation``. Everything else goes into ``training``.
    This keeps similar events from appearing in different splits.

    By default, aim for 150 final-test events, then put 20% of the remaining
    events in validation. Final-test groups must have at most 10 events and
    no dates after 2027-12-31. The seed makes the choices repeatable; the
    dataset hash records which snapshot received these assignments.

    Args:
        rows: Validated events from the private snapshot.
        dataset_sha256: SHA-256 hash of that snapshot.
        seed: Number used to make group selection repeatable.
        final_target: Maximum number of final-test events to select.
        validation_fraction: Share of remaining events to select for validation.
        max_final_group_size: Largest group allowed in final testing.
        latest_final_date: Latest date allowed in a final-test group.

    Returns:
        The split manifest and the groups used to make it.

    Raises:
        ValueError: Invalid settings, fewer than 100 eligible final-test events,
            or no events left for training or validation.
    """
    if (
        type(seed) is not int
        or type(final_target) is not int
        or type(max_final_group_size) is not int
        or not isinstance(validation_fraction, (int, float))
        or not 0 < validation_fraction < 1
        or final_target < 100
        or max_final_group_size < 1
    ):
        raise ValueError("Invalid split settings")
    validate_date(latest_final_date, "latest_final_date")
    grouping = group_demonstrations(rows)
    eligible_final = [
        group_id
        for group_id, members in grouping.groups.items()
        if len(members) <= max_final_group_size
        and all(row["date"] <= latest_final_date for row in members)
    ]
    final_groups, final_rows = _select_groups(
        grouping.groups, eligible_final, final_target, seed, "final"
    )
    if final_rows < 100:
        raise ValueError("Fewer than 100 eligible final-test rows")

    remaining = [group_id for group_id in grouping.groups if group_id not in final_groups]
    validation_target = round(validation_fraction * (len(rows) - final_rows))
    validation_groups, validation_rows = _select_groups(
        grouping.groups, remaining, validation_target, seed, "validation"
    )
    if validation_rows == 0 or len(rows) - final_rows - validation_rows == 0:
        raise ValueError("Split would leave training or validation empty")

    manifest = {
        "schema_version": 1,
        "status": "reserved_pending_group_review",
        "dataset_sha256": dataset_sha256,
        "grouping_policy": "exact-normalized-title+recurrence-key+strong-title-variants-v2",
        "selection_seed": seed,
        "final_target": final_target,
        "validation_fraction": validation_fraction,
        "max_final_group_size": max_final_group_size,
        "latest_final_date": latest_final_date,
        "similar_title_pair_count": len(grouping.similar_title_pairs),
        **_split_assignments(grouping, final_groups, validation_groups, len(rows)),
    }
    return manifest, grouping


def _validation_groups(rows: list[dict], split_manifest: dict) -> dict[str, list[dict]]:
    """Collect only validation events, grouped by demonstration family."""
    assignment = {item["external_id"]: item for item in split_manifest["assignments"]}
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        item = assignment[row["external_id"]]
        if item["split"] == "validation":
            groups[item["group_id"]].append(row)
    return groups


def _pilot_group_priority(members: list[dict]) -> int:
    """Rank groups by health or care titles, then by two-tagged events."""
    if any(HEALTH_PATTERN.search(row["normalized_title"]) for row in members):
        return 0
    if any(len(row["tag_slugs"]) == 2 for row in members):
        return 1
    return 2


def _pilot_row_id(members: list[dict], seed: int, purpose: str) -> str:
    """Pick one event from a group, using a stable tie-breaker."""
    if purpose == "pilot-random-row":
        return min(members, key=lambda row: _rank(seed, purpose, row["external_id"]))["external_id"]
    return min(
        members,
        key=lambda row: (
            0 if HEALTH_PATTERN.search(row["normalized_title"]) else 1,
            0 if len(row["tag_slugs"]) == 2 else 1,
            _rank(seed, purpose, row["external_id"]),
        ),
    )["external_id"]


def choose_pilot_ids(rows: list[dict], split_manifest: dict, *, size: int = 40) -> list[str]:
    """Pick validation events for a trial of the human labeling rules.

    Pick one event per group so a recurring demonstration appears only once.
    For the default 40-event pilot, choose 30 groups using the recorded seed,
    then choose 10 more groups that favor health or care titles and events
    that previously had two tags. For example, a title mentioning "Klinik"
    is favored for those last 10 places. Other groups fill any places left.

    Existing tags help choose examples but are not shown on the review form.
    The same rows and split manifest produce the same list of event IDs.

    Args:
        rows: Validated events from the snapshot.
        split_manifest: Assignments made by ``reserve_splits``.
        size: Number of events to choose; defaults to 40.

    Returns:
        Validation event IDs in the order they should be reviewed.

    Raises:
        ValueError: Size is not a positive integer, or validation has too few groups.
    """
    if type(size) is not int or size < 1:
        raise ValueError("Pilot size must be a positive integer")
    validation_groups = _validation_groups(rows, split_manifest)
    seed = split_manifest["selection_seed"]
    if len(validation_groups) < size:
        raise ValueError("Validation has too few independent groups for the rubric pilot")

    random_count = min(size, round(size * 0.75))
    random_groups = sorted(
        validation_groups, key=lambda group_id: _rank(seed, "pilot-random-group", group_id)
    )[:random_count]
    selected = [
        _pilot_row_id(validation_groups[group_id], seed, "pilot-random-row")
        for group_id in random_groups
    ]
    targeted_groups = sorted(
        (group_id for group_id in validation_groups if group_id not in random_groups),
        key=lambda group_id: (
            _pilot_group_priority(validation_groups[group_id]),
            _rank(seed, "pilot-targeted-group", group_id),
        ),
    )
    for group_id in targeted_groups[: size - len(selected)]:
        selected.append(_pilot_row_id(validation_groups[group_id], seed, "pilot-targeted-row"))
    return selected


def _spreadsheet_cell(value: object) -> object:
    """Keep text beginning with a formula marker literal in spreadsheet apps."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv_bytes(rows: list[dict]) -> bytes:
    """Make a blank, spreadsheet-friendly review form without target labels."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "external_id",
            "date",
            "start_time",
            "title",
            "postcode",
            "venue_tokens",
            "reviewed_tags",
            "uncertainty",
            "source_links",
            "notes",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                _spreadsheet_cell(value)
                for value in (
                    row["external_id"],
                    row["date"],
                    row["start_time"],
                    row["title"],
                    row["postcode"],
                    " | ".join(row["venue_tokens"]),
                    "",
                    "",
                    "",
                    "",
                )
            ]
        )
    return output.getvalue().encode("utf-8-sig")


def _write_new_or_identical(path: Path, content: bytes) -> None:
    """Create a user-private artifact without overwriting later review work."""
    if path.exists():
        if path.read_bytes() == content:
            return
        raise FileExistsError(f"Refusing to overwrite changed private artifact: {path}")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as destination:
        destination.write(content)


def _json_bytes(value: dict) -> bytes:
    """Encode a private manifest with stable, readable formatting."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _pilot_selection_reason(row: dict, index: int, random_count: int) -> str:
    """Explain why one event was placed in the pilot queue."""
    if index < random_count:
        return "random"
    if HEALTH_PATTERN.search(row["normalized_title"]):
        return "health_or_care"
    if len(row["tag_slugs"]) == 2:
        return "historically_two_tags"
    return "targeted_fallback"


def _pilot_selection_record(pilot_ids: list[str], by_id: dict[str, dict], manifest: dict) -> dict:
    """Record the pilot choices without putting labels in the review CSV."""
    random_count = round(len(pilot_ids) * 0.75)
    return {
        "schema_version": 1,
        "dataset_sha256": manifest["dataset_sha256"],
        "split_selection_seed": manifest["selection_seed"],
        "records": [
            {
                "external_id": event_id,
                "selection_reason": _pilot_selection_reason(by_id[event_id], index, random_count),
            }
            for index, event_id in enumerate(pilot_ids)
        ],
    }


def _review_samples(grouping: Grouping) -> tuple[set[str], set[str]]:
    """Choose large groups and groups with differing historical tags for review."""
    large = sorted(
        (group_id for group_id, members in grouping.groups.items() if len(members) > 10),
        key=lambda group_id: (-len(grouping.groups[group_id]), group_id),
    )[:10]
    varied_tags = sorted(
        (
            group_id
            for group_id, members in grouping.groups.items()
            if len({tuple(sorted(row["tag_slugs"])) for row in members}) > 1
        ),
        key=lambda group_id: (-len(grouping.groups[group_id]), group_id),
    )[:5]
    return set(large), set(varied_tags)


def _review_reasons(
    group_id: str,
    members: list[dict],
    variants: list[str],
    large: set[str],
    varied_tags: set[str],
    latest_final_date: str,
) -> list[str]:
    """List the reasons a group needs human inspection."""
    reasons = []
    if group_id in large:
        reasons.append("large_group_sample")
    if len(variants) > 1:
        reasons.append("similar_titles")
    if any(row["date"] > latest_final_date for row in members):
        reasons.append("after_final_test_cutoff")
    if group_id in varied_tags:
        reasons.append("varied_tags_sample")
    return reasons


def _group_review_bytes(grouping: Grouping, latest_final_date: str) -> bytes:
    """Build a review CSV, flagging dates beyond the candidate's saved cutoff."""
    group_review = io.StringIO()
    writer = csv.writer(group_review, lineterminator="\n")
    writer.writerow(
        ["group_id", "row_count", "first_date", "last_date", "title_variants", "reason"]
    )
    large, varied_tags = _review_samples(grouping)
    for group_id, members in sorted(grouping.groups.items()):
        variants = grouping.titles[group_id]
        reasons = _review_reasons(
            group_id, members, variants, large, varied_tags, latest_final_date
        )
        if reasons:
            dates = [row["date"] for row in members]
            writer.writerow(
                [
                    group_id,
                    len(members),
                    min(dates),
                    max(dates),
                    _spreadsheet_cell(" | ".join(variants)),
                    ";".join(reasons),
                ]
            )
    return group_review.getvalue().encode("utf-8-sig")


def _private_split_outputs(
    rows: list[dict], manifest: dict, grouping: Grouping
) -> dict[str, bytes]:
    """Build the manifest and blank review files before writing any of them."""
    assignment = {item["external_id"]: item["split"] for item in manifest["assignments"]}
    final_rows = sorted(
        (row for row in rows if assignment[row["external_id"]] == "final_test"),
        key=lambda row: (row["date"], row["external_id"]),
    )
    pilot_ids = choose_pilot_ids(rows, manifest)
    by_id = {row["external_id"]: row for row in rows}
    pilot_rows = [by_id[event_id] for event_id in pilot_ids]
    return {
        "manifest": _json_bytes(manifest),
        "final_review": _csv_bytes(final_rows),
        "rubric_pilot": _csv_bytes(pilot_rows),
        "pilot_selection": _json_bytes(_pilot_selection_record(pilot_ids, by_id, manifest)),
        "group_review": _group_review_bytes(grouping, manifest["latest_final_date"]),
    }


def save_private_split(
    output_dir: Path, rows: list[dict], manifest: dict, grouping: Grouping
) -> dict[str, Path]:
    """Write the split manifest and private review files without erasing edits.

    Args:
        output_dir: Git-ignored private directory, normally ``data/``.
        rows: The same validated snapshot used to build the manifest.
        manifest: Split assignments from ``reserve_splits``.
        grouping: Group descriptions from ``reserve_splits``.

    Returns:
        Paths to the manifest and four review files. Changed files are never
        overwritten.
    """
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    paths = {
        "manifest": output_dir / "split-manifest.json",
        "final_review": output_dir / "final-review-queue.csv",
        "rubric_pilot": output_dir / "rubric-pilot-queue.csv",
        "pilot_selection": output_dir / "rubric-pilot-selection.json",
        "group_review": output_dir / "group-review.csv",
    }
    outputs = _private_split_outputs(rows, manifest, grouping)
    for name, path in paths.items():
        _write_new_or_identical(path, outputs[name])
    return paths
