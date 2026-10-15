"""Check context encoding in Notebook 05 without loading private records."""

import ast
import json
import re
from pathlib import Path

import pytest
from sklearn.feature_extraction.text import TfidfVectorizer


def feature_functions():
    """Load the notebook's feature functions without executing its experiment."""
    path = Path(__file__).resolve().parents[1] / "notebooks/05_context_and_nearby_places.ipynb"
    notebook = json.loads(path.read_text())
    cell = next(c for c in notebook["cells"] if c["id"] == "context-features")
    tree = ast.parse("".join(cell["source"]))
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    namespace = {"re": re}
    exec(compile(tree, "context-features", "exec"), namespace)  # noqa: S102
    return namespace


def test_context_preserves_monday_midnight_and_postcode_and_namespaces_tokens():
    encode = feature_functions()["context_tokens"]
    row = {
        "weekday": 0,
        "time_bucket": "00:00",
        "postcode": "01234",
        "venue_tokens": ["Platz", "7", "Platz"],
    }
    result = encode(row)
    assert result == [
        "ctx_weekday_0",
        "ctx_time_00_00",
        "ctx_postcode_01234",
        "ctx_venue_7",
        "ctx_venue_platz",
    ]
    analyzer = TfidfVectorizer().build_analyzer()
    assert analyzer(" ".join(result)) == result
    assert encode({**row, "venue_tokens": list(reversed(row["venue_tokens"]))}) == result


def test_missing_context_is_explicit_and_labels_never_enter_features():
    namespace = feature_functions()
    encode, text = namespace["context_tokens"], namespace["feature_text"]
    row = {
        "title": "Sichere Radwege",
        "weekday": None,
        "time_bucket": "",
        "postcode": None,
        "venue_tokens": [],
    }
    assert encode(row) == [
        "ctx_weekday_missing",
        "ctx_time_missing",
        "ctx_postcode_missing",
        "ctx_venue_missing",
    ]
    assert text(row, "F0") == row["title"]
    enriched = {
        **row,
        "tag_slugs": ["secret_label"],
        "reviewed_tags": "another_label",
        "external_id": "private_id",
    }
    assert text(enriched, "F3") == text(row, "F3")
    assert text(enriched, "F0") == text(row, "F0")
    assert row["title"] == "Sichere Radwege"
    with pytest.raises(ValueError, match="F0 or F3"):
        text(row, "F4")
