"""Synthetic checks that comparisons use matching inputs and correctly ordered predictions."""

import json

import pytest

from notebooks.tools import aligned_predictions, comparison_row, matching_report


def test_report_match_skips_newer_incompatible_data(tmp_path):
    candidate = {
        "baseline_version": "v1",
        "snapshot_sha256": "snapshot",
        "taxonomy_version": "v2",
        "selection_sha256": "selection",
        "fingerprints": {"pilot": "approved"},
    }
    (tmp_path / "01.json").write_text(json.dumps(candidate))
    for i, change in enumerate(
        [
            {"snapshot_sha256": "other"},
            {"taxonomy_version": "old"},
            {"selection_sha256": "other"},
            {"fingerprints": {"pilot": "changed"}},
        ],
        2,
    ):
        (tmp_path / f"0{i}.json").write_text(json.dumps({**candidate, **change}))
    args = {
        "source": {"content_sha256": "snapshot", "taxonomy_version": "v2"},
        "selection": {"selection_sha256": "selection"},
        "fingerprints": {"pilot": "approved"},
    }
    path, report = matching_report(tmp_path, "baseline_version", **args)
    assert path.name == "01.json" and report == candidate
    assert matching_report(tmp_path, "model_version", required=False, **args) is None
    with pytest.raises(FileNotFoundError):
        matching_report(tmp_path, "model_version", **args)


def test_alignment_reorders_without_changing_tags():
    predictions = [{"external_id": "b", "predicted": []}, {"external_id": "a", "predicted": ["x"]}]
    assert aligned_predictions(predictions, [{"external_id": "a"}, {"external_id": "b"}]) == [
        ["x"],
        [],
    ]


@pytest.mark.parametrize(
    "prediction_ids,row_ids",
    [(["a", "a"], ["a"]), (["a"], ["a", "b"]), (["a", "b"], ["a"]), (["a"], ["a", "a"])],
)
def test_alignment_rejects_missing_extra_or_duplicate_events(prediction_ids, row_ids):
    with pytest.raises(ValueError):
        aligned_predictions(
            [{"external_id": i, "predicted": []} for i in prediction_ids],
            [{"external_id": i} for i in row_ids],
        )


def test_comparison_display_preserves_undefined_precision_and_optional_column():
    metrics = {
        "records": 3,
        "micro_precision": None,
        "micro_recall": 0,
        "micro_f1": 0,
        "coverage": 0,
        "exact_match": 0,
        "more_than_two": 0,
    }
    assert comparison_row("model", metrics) == (
        "model",
        3,
        "undefined",
        "0.0%",
        "0.0%",
        "0.0%",
        "0.0%",
        0,
    )
    assert len(comparison_row("model", metrics, include_exact_match=False)) == 7
