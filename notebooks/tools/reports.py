"""Match saved experiments and align predictions without choosing model policies."""

import json
from pathlib import Path


def matching_report(
    directory: Path,
    kind: str,
    *,
    source: dict,
    selection: dict,
    fingerprints: dict[str, str],
    required: bool = True,
) -> tuple[Path, dict] | None:
    """Find the newest report using the same data, taxonomy, selection and input files.

    Args:
        directory: Private report folder with timestamp-named JSON files.
        kind: Required report marker, such as baseline_version or model_version.
        source: Loaded source manifest containing content_sha256 and taxonomy_version.
        selection: Saved representative selection containing selection_sha256.
        fingerprints: Expected hashes of all inputs needed for this comparison.
        required: Raise when no report matches; False returns None for optional tables.

    The caller still checks experiment-specific settings and computes comparisons.
    Invalid JSON raises rather than silently ignoring a damaged report.
    """
    for path in sorted(directory.glob("*.json"), reverse=True):
        candidate = json.loads(path.read_text(encoding="utf-8"))
        if (
            kind in candidate
            and candidate.get("snapshot_sha256") == source["content_sha256"]
            and candidate.get("taxonomy_version") == source["taxonomy_version"]
            and candidate.get("selection_sha256") == selection["selection_sha256"]
            and all(candidate.get("fingerprints", {}).get(k) == v for k, v in fingerprints.items())
        ):
            return path, candidate
    if required:
        raise FileNotFoundError(
            f"No matching report in {directory.name}; rerun its source notebook on these inputs"
        )
    return None


def aligned_predictions(predictions: list[dict], rows: list[dict]) -> list[list[str]]:
    """Return saved tag predictions in the requested event order, rejecting missing/extra IDs.

    Each input must contain each event exactly once. This prevents duplicate IDs
    from silently overwriting predictions and comparing answers with the wrong row.
    No labels or scores are changed.
    """
    ids = [row["external_id"] for row in rows]
    by_id = {item["external_id"]: item["predicted"] for item in predictions}
    if len(set(ids)) != len(ids) or len(by_id) != len(predictions) or set(by_id) != set(ids):
        raise ValueError("Comparison report must contain each validation representative once")
    return [by_id[event_id] for event_id in ids]
