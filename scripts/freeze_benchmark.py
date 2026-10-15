"""Verify reviewed keep-together decisions and freeze the existing split in place."""

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from demo_logic.benchmark import (
    FILES,
    _csv,
    assignment_fingerprint,
    decision_fingerprint,
    load_benchmark,
)
from demo_logic.snapshot import load_snapshot


def freeze_benchmark(
    data_dir: Path,
    backup_dir: Path,
    reviewer: str,
    *,
    expected_groups: int = 29,
    write: bool = False,
) -> dict:
    """Check the complete bundle, then optionally record its frozen membership.

    Args:
        data_dir: Private directory holding the snapshot and benchmark folder.
        backup_dir: Private directory for one copy of the pre-freeze manifest.
        reviewer: Person who approved the group decisions, recorded for provenance.
        expected_groups: Number of reviewed event types expected in this task.
        write: False previews the checks; True atomically replaces only the manifest.

    Returns:
        Aggregate counts and freeze fingerprints, without event titles or IDs.

    Raises:
        ValueError: Files disagree, a decision is unresolved, or the review count
            differs from the expected count. Source changes during preparation
            also stop the operation. No groups are regenerated or reassigned.

    A verified already-frozen bundle is a no-op. Review CSVs, snapshot bytes,
    final labels, and pilot selections are never rewritten. The backup is a
    recovery copy, not another active split candidate.
    """
    if not reviewer.strip():
        raise ValueError("Provide the person who reviewed the group decisions")
    directory = data_dir / "benchmark"
    paths = [data_dir / "dataset.jsonl", data_dir / "manifest.json"] + [
        directory / name for name in FILES.values()
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    rows, snapshot = load_snapshot(data_dir / "dataset.jsonl", data_dir / "manifest.json")
    bundle = load_benchmark(directory, rows, snapshot["content_sha256"])
    reviews = _csv(bundle.paths["group_review"], {"group_id", "decision"})
    if len(reviews) != expected_groups:
        raise ValueError(f"Expected {expected_groups} reviewed groups, found {len(reviews)}")
    decisions_hash = decision_fingerprint(reviews)
    manifest = bundle.manifest
    if manifest["status"] not in {"reserved_pending_group_review", "frozen"}:
        raise ValueError("Unsupported split status; reconcile it before freezing")
    record = (
        manifest.get("freeze")
        if manifest["status"] == "frozen"
        else {
            "version": 1,
            "frozen_at": datetime.now(UTC).isoformat(),
            "reviewed_by": reviewer.strip(),
            "reviewed_group_count": len(reviews),
            "reviewed_occurrence_count": sum(
                len(bundle.groups[row["group_id"]]) for row in reviews
            ),
            "assignments_sha256": assignment_fingerprint(manifest["assignments"]),
            "decisions_sha256": decisions_hash,
            "policy": "Each reviewed event type stays together; types and dated occurrences remain distinct.",
            "labels_frozen": False,
        }
    )
    report = {
        "status": "already_frozen" if manifest["status"] == "frozen" else "ready_to_freeze",
        "dataset_sha256": snapshot["content_sha256"],
        "taxonomy_version": snapshot["taxonomy_version"],
        "split_counts": manifest["split_counts"],
        "group_counts": manifest["group_counts"],
        "pilot_count": len(bundle.pilot_ids),
        "assignments_changed": False,
        "freeze": record,
    }
    if not write or manifest["status"] == "frozen":
        return report
    if any(
        hashlib.sha256(path.read_bytes()).hexdigest() != digest for path, digest in before.items()
    ):
        raise ValueError("Benchmark files changed during verification; rerun after edits are saved")
    manifest_path = bundle.paths["manifest"]
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = backup_dir / f"split-manifest-{before[manifest_path][:16]}.json"
    original = manifest_path.read_bytes()
    if backup.exists():
        if backup.read_bytes() != original:
            raise ValueError("An existing backup has different contents")
    else:
        with backup.open("xb") as output:
            os.chmod(backup, 0o600)
            output.write(original)
    updated = {**manifest, "status": "frozen", "freeze": record}
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".split-freeze-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(updated, output, ensure_ascii=False, sort_keys=True, indent=2)
            output.write("\n")
        os.replace(temporary, manifest_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    report["status"] = "frozen"
    return report


def main() -> None:
    """Preview by default; require --write to persist the verified freeze record."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--backup-dir", type=Path, default=Path("artifacts/split-freeze-backups"))
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--expected-groups", type=int, default=29)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            freeze_benchmark(
                args.data_dir,
                args.backup_dir,
                args.reviewer,
                expected_groups=args.expected_groups,
                write=args.write,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
