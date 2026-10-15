"""Prepare a separate taxonomy-v2 benchmark bundle; never overwrite the active one."""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from demo_logic.benchmark import load_benchmark
from demo_logic.dataset import canonical_bytes
from demo_logic.snapshot import load_snapshot
from demo_logic.taxonomy import V1_TO_V2


def _json_bytes(value: dict) -> bytes:
    """Encode readable, deterministic metadata without exposing row text."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _review_bytes(path: Path) -> bytes:
    """Translate exact reviewed tag tokens, preserving notes and other cell contents.

    Both supported spreadsheet delimiters and tag separators are accepted.
    Only the tag name in a per-tag uncertainty entry is translated; its score
    and the reviewer's narrative are left intact. Empty final-review cells stay empty.
    """
    with path.open(encoding="utf-8-sig", newline="") as source:
        header = source.readline()
        source.seek(0)
        delimiter = ";" if header.count(";") > header.count(",") else ","
        reader = csv.DictReader(source, delimiter=delimiter)
        fields = reader.fieldnames
        records = list(reader)
    for row in records:
        for old, new in V1_TO_V2.items():
            row["reviewed_tags"] = re.sub(
                rf"(?<![\w-]){re.escape(old)}(?![\w-])", new, row["reviewed_tags"]
            )
            row["uncertainty"] = re.sub(rf"\b{re.escape(old)}(?=\s*:)", new, row["uncertainty"])
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, delimiter=delimiter)
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue().encode("utf-8-sig")


def plan_migration(source: Path) -> tuple[dict[str, bytes], dict]:
    """Validate a v1 snapshot/bundle and prepare a v2 copy entirely in memory.

    Args:
        source: Private data directory containing dataset.jsonl, manifest.json,
            and the complete benchmark subdirectory.

    Returns:
        Relative output paths and bytes, plus a publication-safe aggregate report.
        IDs, features, review decisions, and split assignments are preserved.
        Only the conflict slug is mechanically translated. Politics and other
        semantic changes remain subject to review; they are never guessed.

    Raises:
        ValueError: The source is not taxonomy v1 or its bundle is inconsistent.
        FileNotFoundError: An input artifact is missing.
    """
    rows, manifest = load_snapshot(source / "dataset.jsonl", source / "manifest.json")
    if manifest["taxonomy_version"] != "v1":
        raise ValueError("Migration requires a taxonomy-v1 source; do not migrate v2 twice")
    bundle = load_benchmark(source / "benchmark", rows, manifest["content_sha256"])
    migrated = [
        {
            **row,
            "taxonomy_version": "v2",
            "tag_slugs": sorted(V1_TO_V2.get(tag, tag) for tag in row["tag_slugs"]),
        }
        for row in rows
    ]
    data = b"".join(canonical_bytes(row) for row in migrated)
    fingerprint = hashlib.sha256(data).hexdigest()
    report = {
        "from_taxonomy": "v1",
        "to_taxonomy": "v2",
        "source_content_sha256": manifest["content_sha256"],
        "content_sha256": fingerprint,
        "row_count": len(rows),
        "rename_map": V1_TO_V2,
        "renamed_assignments": sum(tag in V1_TO_V2 for row in rows for tag in row["tag_slugs"]),
        "politics_rows_requiring_scope_review": sum("politics" in row["tag_slugs"] for row in rows),
        "semantic_review_status": "pending",
        "split_assignments_changed": False,
    }
    updated_manifest = {
        **manifest,
        "taxonomy_version": "v2",
        "content_sha256": fingerprint,
        "tag_counts": dict(Counter(t for row in migrated for t in row["tag_slugs"])),
        "taxonomy_migration": report,
    }
    split = {**bundle.manifest}
    split["dataset_sha256"] = fingerprint
    split["taxonomy_version"] = "v2"
    split["taxonomy_migration"] = report
    by_id = {row["external_id"]: row for row in migrated}
    counts = defaultdict(Counter)
    for assignment in split["assignments"]:
        row = by_id[assignment["external_id"]]
        counts[assignment["split"]].update(row["tag_slugs"])
    split["tag_counts"] = {name: dict(values) for name, values in counts.items()}
    selection = json.loads((source / "benchmark/rubric-pilot-selection.json").read_text())
    selection["dataset_sha256"] = fingerprint
    selection["taxonomy_version"] = "v2"
    files = {
        "dataset.jsonl": data,
        "manifest.json": _json_bytes(updated_manifest),
        "benchmark/split-manifest.json": _json_bytes(split),
        "benchmark/rubric-pilot-selection.json": _json_bytes(selection),
        "benchmark/group-review.csv": (source / "benchmark/group-review.csv").read_bytes(),
        "taxonomy-migration-report.json": _json_bytes(report),
    }
    for name in ("rubric-pilot-queue.csv", "final-review-queue.csv"):
        files[f"benchmark/{name}"] = _review_bytes(source / "benchmark" / name)
    if (source / "source-manifest.json").exists():
        files["source-manifest.json"] = (source / "source-manifest.json").read_bytes()
    return files, report


def migrate(source: Path, destination: Path, *, write: bool = False) -> dict:
    """Dry-run by default, or write and validate a new owner-only bundle.

    Destination must not exist and must not be inside the source directory.
    A failed write is removed; the input bundle is never modified. Callers
    activate a reviewed output separately. This function never contacts a server.
    """
    source, destination = source.resolve(), destination.resolve()
    if destination == source or source in destination.parents or destination.exists():
        raise ValueError("Use a new destination outside the source directory")
    files, report = plan_migration(source)
    if not write:
        return report
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        for relative, content in files.items():
            path = destination / relative
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
        rows, manifest = load_snapshot(destination / "dataset.jsonl", destination / "manifest.json")
        load_benchmark(destination / "benchmark", rows, manifest["content_sha256"])
    except Exception:
        shutil.rmtree(destination)
        raise
    return report


def main() -> None:
    """Print aggregate migration impact; --write explicitly prepares a separate copy."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.source_dir, args.output_dir, write=args.write), indent=2))


if __name__ == "__main__":
    main()
