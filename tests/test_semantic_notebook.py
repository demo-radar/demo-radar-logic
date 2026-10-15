"""Check the actual semantic notebook logic with synthetic data and no model download."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from sklearn.model_selection import GroupShuffleSplit

from demo_logic.evaluation import multilabel_metrics, parse_review_tags
from notebooks.tools import fingerprint


def notebook_cells():
    """Read source cells without running private-data loading or expensive inference."""
    path = Path(__file__).resolve().parents[1] / "notebooks/06_semantic_models.ipynb"
    return {c["id"]: "".join(c["source"]) for c in json.loads(path.read_text())["cells"]}


def functions_from_notebook():
    """Load only pure helpers so CI exercises notebook code without importing PyTorch."""
    namespace = {"np": np, "json": json, "tags": ["a", "b", "c"]}
    for cell_id in ("semantic-score-functions", "semantic-thresholds"):
        tree = ast.parse(notebook_cells()[cell_id])
        tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        exec(compile(tree, cell_id, "exec"), namespace)  # noqa: S102
    return namespace


def test_nli_scores_use_named_classes_and_normalize_each_tag_independently():
    score = functions_from_notebook()["nli_tag_scores"]
    logits = np.array([[3.0, 1.0, 0.0], [3.0, 1.0, 0.0]])
    first, neutral = score(logits, {"entailment": 0, "neutral": 1, "contradiction": 2})
    reordered, other_neutral = score(
        logits[:, [2, 0, 1]], {"contradiction": 0, "entailment": 1, "neutral": 2}
    )
    np.testing.assert_allclose(first, reordered)
    np.testing.assert_allclose(neutral, other_neutral)
    assert np.all(first > 0.95)  # Both tags can qualify; scores do not sum to one.
    assert np.all(first < 1)


def test_neutral_is_visible_even_when_binary_tag_score_is_high():
    score = functions_from_notebook()["nli_tag_scores"]
    binary, neutral = score(
        [[1001.0, 1100.0, 1000.0]], {"entailment": 0, "neutral": 1, "contradiction": 2}
    )
    assert binary[0] == pytest.approx(0.73105858)
    assert neutral[0] > 0.99


@pytest.mark.parametrize("logits", [[[np.nan, 0, 1]], [[np.inf, 0, 1]], [[1, 2]], [1, 2, 3]])
def test_invalid_logits_stop_scoring(logits):
    with pytest.raises(ValueError):
        functions_from_notebook()["nli_tag_scores"](
            logits, {"entailment": 0, "neutral": 1, "contradiction": 2}
        )


def test_duplicate_class_mapping_is_rejected():
    with pytest.raises(ValueError):
        functions_from_notebook()["nli_tag_scores"](
            [[1, 2, 3]], {"entailment": 0, "neutral": 0, "contradiction": 2}
        )


def test_semantic_output_policy_keeps_exact_ties_and_counts_abstention():
    select = functions_from_notebook()["select_tags"]
    assert select([0.9, 0.8, 0.8], 0.8) == ["a", "b", "c"]
    assert select([0.9, 0.8, 0.8], 0.8, include_ties=False) == ["a", "b"]
    assert select([0.9, 0.8, 0.799999], 0.8) == ["a", "b"]
    assert select([0.2, 0.1, 0.1], 0.3) == []


def test_cache_fingerprint_changes_with_title_or_hypothesis():
    original = {"title": "Für sichere Radwege", "hypothesis": "Verkehr", "revision": "abc"}
    assert fingerprint(original) == fingerprint(dict(reversed(list(original.items()))))
    for key in original:
        assert fingerprint(original) != fingerprint({**original, key: "changed"})


def test_only_validation_representatives_reach_semantic_scoring(tmp_path):
    """A final record lacks title/labels; touching either would fail this data-loading cell."""
    rows = [{"external_id": "training"}, {"external_id": "final"}]
    rows += [
        {"external_id": f"v{i}", "title": f"Synthetic event {i}", "tag_slugs": ["a"]}
        for i in range(40)
    ]
    assignments = [
        {
            "external_id": row["external_id"],
            "group_id": f"g-{i}",
            "split": row["external_id"] if i < 2 else "validation",
        }
        for i, row in enumerate(rows)
    ]
    bundle = SimpleNamespace(
        manifest={"status": "frozen", "assignments": assignments},
        paths={"manifest": tmp_path / "split", "rubric_pilot": tmp_path / "pilot"},
    )

    def read_review(path, required):
        assert path == bundle.paths["rubric_pilot"], "Must not open final-review answers"
        return [{"external_id": f"v{i}", "reviewed_tags": "a"} for i in range(40)]

    namespace = {
        "root": tmp_path,
        "load_snapshot": lambda *args: (
            rows,
            {"content_sha256": "snapshot", "taxonomy_version": "v2"},
        ),
        "load_benchmark": lambda *args: bundle,
        "representative_selection": lambda bundle: {"version": "test", "records": rows},
        "save_private_json": lambda path, data: path,
        "topic_tags": lambda version: ["a", "b"],
        "_csv": read_review,
        "parse_review_tags": parse_review_tags,
        "file_sha256": lambda path: "synthetic-hash",
        "GroupShuffleSplit": GroupShuffleSplit,
        "show": lambda *args: None,
    }
    exec(notebook_cells()["semantic-data"], namespace)  # noqa: S102
    assert len(namespace["validation"]) == 40
    assert namespace["training_count"] == 1
    assert all(row["external_id"].startswith("v") for row in namespace["validation"])
    assert not set(namespace["tune_index"]) & set(namespace["check_index"])


def test_excluding_human_rights_frees_a_slot_without_changing_other_scores():
    namespace = functions_from_notebook()
    namespace["tags"] = ["a", "human-rights", "b"]
    select = namespace["select_tags"]
    assert select([0.8, 0.9, 0.7], 0.5) == ["human-rights", "a"]
    assert select([0.8, -np.inf, 0.7], 0.5) == ["a", "b"]
    assert select([0.8, -np.inf, 0.4], 0.5) == ["a"]


def test_eleven_tag_diagnostic_removes_hr_on_both_sides_but_keeps_events():
    namespace = {
        "multilabel_metrics": multilabel_metrics,
        "tags": ["a", "human-rights"],
        "remaining_tags": ["a"],
    }
    tree = ast.parse(notebook_cells()["hr-evaluate"])
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    exec(compile(tree, "hr-evaluate", "exec"), namespace)  # noqa: S102
    metric = namespace["hr_metrics"]
    reference = [["human-rights"], ["a"]]
    predicted = [["human-rights"], []]
    reduced = metric(reference, predicted, [0, 1], remaining_only=True)
    assert reduced["records"] == 2
    assert reduced["coverage"] == 0
    assert reduced["micro_recall"] == 0
    full = metric(reference, predicted, [0, 1])
    assert full["coverage"] == 0.5
    assert full["micro_recall"] == 0.5


def test_diagnostic_full_probabilities_and_binary_score_use_different_denominators():
    namespace = functions_from_notebook()
    tree = ast.parse(notebook_cells()["synthetic-diagnostic"])
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    exec(compile(tree, "synthetic-diagnostic", "exec"), namespace)  # noqa: S102
    result = namespace["diagnostic_probabilities"](
        [[1001.0, 1100.0, 1000.0]], {"entailment": 0, "neutral": 1, "contradiction": 2}
    )
    assert sum(result[k] for k in ["support", "neutral", "contradiction"]) == pytest.approx(1)
    assert result["neutral"] > 0.99
    assert result["support"] < 0.01
    assert result["tag_score"] == pytest.approx(
        result["support"] / (result["support"] + result["contradiction"])
    )
