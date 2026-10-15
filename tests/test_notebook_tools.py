"""Synthetic checks for shared notebook tools; no private data or model downloads."""

import hashlib
import json

import pytest

from notebooks.tools import file_sha256, notebook_sha256, table_html, verify_sha256
from notebooks.tools.hashes import fingerprint
from notebooks.tools.review import write_nli_review


def test_file_verification_detects_changed_unicode_content(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("Öffentliche Gebete (Du&#703;)", encoding="utf-8")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert file_sha256(path) == verify_sha256(path, expected) == expected
    path.write_text("Changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Fingerprint mismatch"):
        verify_sha256(path, expected)


def test_notebook_fingerprint_ignores_outputs_but_detects_source_changes(tmp_path):
    path = tmp_path / "example.ipynb"
    cells = [{"cell_type": "code", "source": ["x = 1"], "outputs": []}]
    path.write_text(json.dumps({"cells": cells}))
    hashes = {scheme: notebook_sha256(path, scheme=scheme) for scheme in ["text", "cells"]}
    cells[0]["outputs"] = [{"text": "private result"}]
    path.write_text(json.dumps({"cells": cells}))
    assert all(notebook_sha256(path, scheme=s) == h for s, h in hashes.items())
    cells[0]["source"] = ["x = 2"]
    path.write_text(json.dumps({"cells": cells}))
    assert all(notebook_sha256(path, scheme=s) != h for s, h in hashes.items())


def test_html_values_stay_literal():
    result = table_html(["<header>"], [["<script>alert(1)</script>"]])
    assert "<script>" not in result
    assert "&lt;script&gt;" in result and "&lt;header&gt;" in result


def test_review_exports_only_check_disagreements_and_preserves_notes(tmp_path):
    rows = [
        {"external_id": name, "title": "<unsafe>", "tag_slugs": ["a"]} for name in ["check", "tune"]
    ]
    report = {
        "run_id": "synthetic",
        "check_ids": ["check"],
        "threshold_selection_ids": ["tune"],
        "inference_settings": {"tags": ["a", "b"]},
        "policies": [
            {
                "policy": "include_cutoff_ties",
                "threshold": 0.35,
                "predictions": [
                    {"external_id": r["external_id"], "predicted": ["b"]} for r in rows
                ],
            }
        ],
        "events": [
            {
                "external_id": r["external_id"],
                "identity": {"title_sha256": fingerprint(r["title"])},
                "scores": [0.1, 0.8],
                "neutral_probabilities": [0.2, 0.9],
            }
            for r in rows
        ],
    }
    path = write_nli_review(tmp_path / "review.md", report, rows)
    text = path.read_text()
    assert "1 disagreements out of 1" in text
    assert "## 1. check" in text and "## 2." not in text
    assert "&lt;unsafe&gt;" in text and "<unsafe>" not in text
    path.write_text(text + "Reviewer's decision")
    with pytest.raises(FileExistsError):
        write_nli_review(path, report, rows)
    assert path.read_text().endswith("Reviewer's decision")
    rows[0]["title"] = "Changed"
    with pytest.raises(ValueError, match="Title changed"):
        write_nli_review(tmp_path / "other.md", report, rows)
