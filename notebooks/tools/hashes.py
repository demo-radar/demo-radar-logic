"""Shared fingerprints for experiment inputs, notebook source, and cached settings."""

import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    """Hash file bytes in a stream so large model weights do not fill memory.

    Missing files raise FileNotFoundError. The file is never modified.
    """
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_sha256(path: Path, expected: str) -> str:
    """Check a pinned file in one call and return its verified SHA-256.

    Args:
        path: File whose bytes must match the expected version.
        expected: Previously approved hexadecimal SHA-256 digest.

    Raises:
        ValueError: Content differs; inspect the change before updating the pin.
    """
    actual = file_sha256(path)
    if actual != expected:
        raise ValueError(
            f"Fingerprint mismatch for {path.name}; review the change before updating its pin"
        )
    return actual


def fingerprint(value: object) -> str:
    """Hash JSON-compatible settings consistently, including Unicode text.

    Sorted dictionary keys make key order irrelevant. Non-finite numbers and
    non-JSON objects are rejected. This preserves Notebook 06's existing cache keys.
    """
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def notebook_sha256(path: Path, *, scheme: str = "text") -> str:
    """Fingerprint notebook source while ignoring outputs and execution counts.

    ``text`` preserves the scheme used by Notebooks 04 and 06. ``cells`` preserves
    Notebook 03's earlier cell-type/source serialization. Keeping both explicit
    avoids changing report conventions as part of a helper-only refactor.
    """
    cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
    if scheme == "text":
        content = "".join("".join(cell.get("source", [])) for cell in cells)
    elif scheme == "cells":
        content = json.dumps(
            [{"cell_type": c["cell_type"], "source": c["source"]} for c in cells],
            ensure_ascii=False,
            sort_keys=True,
        )
    else:
        raise ValueError("Notebook hash scheme must be 'text' or 'cells'")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
