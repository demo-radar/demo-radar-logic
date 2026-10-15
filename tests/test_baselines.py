"""Synthetic checks for leakage, tag-selection policy and evaluation arithmetic."""

import ast
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from statistics import median
from time import perf_counter

import pytest


def notebook_cells():
    """Read the actual experiment cells; no private data or Jupyter kernel needed."""
    path = Path(__file__).resolve().parents[1] / "notebooks/03_simple_baselines.ipynb"
    return {
        cell["id"]: "".join(cell["source"])
        for cell in json.loads(path.read_text())["cells"]
        if cell["cell_type"] == "code"
    }


def baseline_namespace():
    """Load rule definitions from the notebook without executing its experiment."""
    namespace = {"html": html, "re": re, "unicodedata": unicodedata, "Counter": Counter}
    for cell_id in ("rule-selection", "rule-common", "rule-keywords", "rule-history"):
        tree = ast.parse(notebook_cells()[cell_id])
        tree.body = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            or (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id in {"KEYWORDS", "COMPILED", "BASELINE_VERSION"}
                    for target in node.targets
                )
            )
        ]
        exec(compile(tree, cell_id, "exec"), namespace)  # noqa: S102 — execute local notebook definitions
    return namespace


rules = baseline_namespace()
fit_most_common = rules["fit_most_common"]
keyword_scores = rules["keyword_scores"]
lookup_scores = rules["lookup_scores"]
select_tags = rules["select_tags"]
from demo_logic.evaluation import multilabel_metrics, parse_review_tags


def test_cutoff_ties_and_abstention():
    scores = {"a": 3, "b": 2, "c": 2, "d": 0}
    assert select_tags(scores) == ["a", "b", "c"]
    assert select_tags(scores, include_ties=False) == ["a", "b"]
    assert select_tags({"a": 0}) == []


def test_common_tag_counts_events_and_stable_ties():
    assert fit_most_common([{"tag_slugs": ["b", "b", "a"]}]) == "a"
    with pytest.raises(ValueError):
        fit_most_common([])


def test_demo_radar_regex_normalization_and_binary_scores():
    assert keyword_scores("Neue Radwege jetzt")["mobility"] == 1
    assert keyword_scores("Glaubensfreiheit und Gebete")["religion"] == 1
    assert keyword_scores("Für Gesundheit")["social-issues"] == 1
    assert keyword_scores("Bäume und Müll")["environment"] == 1
    assert keyword_scores("Schulweg")["mobility"] == 1
    assert keyword_scores("Schulweg")["education"] == 1
    assert keyword_scores("Kultur in China")["international-politics"] == 0
    assert keyword_scores("Menschenrechte in China")["international-politics"] == 1
    assert keyword_scores("Demokratie in Deutschland").get("politics", 0) == 0
    assert not any(keyword_scores("Unbekanntes Thema").values())


def test_lookup_excludes_same_day_future_and_other_groups():
    event = {"group_id": "x", "date": "2026-05-02", "tag_slugs": ["secret"]}
    history = [
        {"group_id": "x", "date": "2026-05-01", "tag_slugs": ["a"]},
        {"group_id": "x", "date": "2026-05-02", "tag_slugs": ["secret"]},
        {"group_id": "x", "date": "2026-05-03", "tag_slugs": ["future"]},
        {"group_id": "other", "date": "2026-05-01", "tag_slugs": ["other"]},
    ]
    assert lookup_scores(history, event) == {"a": 1}
    history.append({"group_id": "x", "date": "2026-05-01", "tag_slugs": ["b"]})
    assert lookup_scores(history, event) == {}
    assert lookup_scores(history, {**event, "group_id": "new"}) == {}


def test_micro_metrics_include_missed_tags_and_abstentions():
    result = multilabel_metrics([["a", "b"], ["a"]], [["a"], []], ["a", "b", "c"])
    assert result["micro_precision"] == 1
    assert result["micro_recall"] == pytest.approx(1 / 3)
    assert result["micro_f1"] == 0.5
    assert result["coverage"] == 0.5
    assert result["per_tag"]["b"]["fn"] == 1
    assert result["per_tag"]["c"]["tn"] == 2
    assert result["macro_recall_supported"] == 0.25


def test_no_predictions_have_undefined_precision_and_zero_recall():
    result = multilabel_metrics([["a"]], [[]], ["a"])
    assert result["micro_precision"] is None
    assert result["micro_recall"] == 0
    assert result["micro_f1"] == 0


def test_review_tags_keep_all_human_labels_and_reject_unknowns():
    assert parse_review_tags("a,b;c", {"a", "b", "c"}) == ["a", "b", "c"]
    for value in ("", "a,a", "a,unknown"):
        with pytest.raises(ValueError):
            parse_review_tags(value, {"a"})


def test_metrics_reject_silent_truncation_and_unknown_tags():
    with pytest.raises(ValueError):
        multilabel_metrics([["a"]], [], ["a"])
    with pytest.raises(ValueError):
        multilabel_metrics([["a"]], [["b"]], ["a"])


def test_notebook_never_fits_or_scores_final_labels(tmp_path):
    from types import SimpleNamespace

    from demo_logic.benchmark import representative_selection
    from demo_logic.notebook_support import save_private_json
    from demo_logic.taxonomy import topic_tags

    class FinalRecord(dict):
        def __getitem__(self, key):
            if key == "tag_slugs":
                raise AssertionError("Final-test labels must not enter the experiment")
            return super().__getitem__(key)

    rows = [
        {
            "external_id": "train",
            "title": "Train event",
            "date": "2026-01-01",
            "tag_slugs": ["housing"],
        },
        {
            "external_id": "val",
            "title": "Klima jetzt",
            "date": "2026-02-01",
            "tag_slugs": ["environment"],
        },
        FinalRecord(external_id="final", title="Final event", date="2026-03-01"),
    ]
    manifest = {
        "dataset_sha256": "synthetic",
        "status": "frozen",
        "assignments": [
            {"external_id": event_id, "group_id": event_id, "split": split}
            for event_id, split in [
                ("train", "training"),
                ("val", "validation"),
                ("final", "final_test"),
            ]
        ],
    }
    paths = {"manifest": tmp_path / "split.json", "rubric_pilot": tmp_path / "pilot.csv"}
    cells = notebook_cells()
    namespace = baseline_namespace()
    namespace.update(
        {
            "root": tmp_path,
            "load_snapshot": lambda *args: (
                rows,
                {"content_sha256": "synthetic", "taxonomy_version": "v2"},
            ),
            "load_benchmark": lambda *args: SimpleNamespace(
                manifest=manifest,
                paths=paths,
                pilot_ids=["val"],
                groups={row["external_id"]: [row] for row in rows},
            ),
            "representative_selection": representative_selection,
            "save_private_json": save_private_json,
            "_csv": lambda *args: [{"external_id": "val", "reviewed_tags": "environment"}],
            "topic_tags": topic_tags,
            "parse_review_tags": parse_review_tags,
            "multilabel_metrics": multilabel_metrics,
            "perf_counter": perf_counter,
            "median": median,
        }
    )

    def run_development():
        for cell_id in (
            "load-development",
            "rule-common",
            "compare-development",
            "compare-history",
        ):
            exec(compile(cells[cell_id], cell_id, "exec"), namespace)  # noqa: S102 — synthetic notebook check
        return namespace["runs"]

    runs = run_development()
    assert namespace["common"] == "housing"
    assert len(namespace["validation"]) == 1
    assert len(namespace["later"]) == 0
    assert all(run["historical_agreement"]["records"] == 1 for run in runs)
    original_predictions = [run["predictions"] for run in runs]
    rows[1]["tag_slugs"] = ["religion"]
    rerun = run_development()
    assert [run["predictions"] for run in rerun] == original_predictions
    manifest["status"] = "candidate"
    with pytest.raises(ValueError, match="locked"):
        run_development()
