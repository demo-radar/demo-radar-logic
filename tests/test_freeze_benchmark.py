"""Freeze preserves saved work and rejects changed or unresolved group decisions."""

import importlib.util
import json
from pathlib import Path

import pytest

from demo_logic.benchmark import FILES, load_benchmark
from tests.test_benchmark import bundle, fingerprint, read_csv, write_csv, write_json  # noqa: F401

spec = importlib.util.spec_from_file_location(
    "freeze_command", Path(__file__).parents[1] / "scripts/freeze_benchmark.py"
)
freeze_command = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freeze_command)


@pytest.fixture
def reviewed_bundle(request, monkeypatch):
    directory, rows, manifest, paths = request.getfixturevalue("bundle")
    saved = load_benchmark(directory, rows, "synthetic-fingerprint")
    group_id, members = next(iter(saved.groups.items()))
    fields, _ = read_csv(paths["group_review"])
    fields += [name for name in ["decision", "preferred_title"] if name not in fields]
    record = dict.fromkeys(fields, "")
    record.update(
        group_id=group_id,
        row_count=str(len(members)),
        first_date=members[0]["date"],
        last_date=members[0]["date"],
        decision="same event",
        preferred_title="Readable type",
    )
    write_csv(paths["group_review"], fields, [record])
    data = directory / "data"
    target = data / "benchmark"
    target.mkdir(parents=True)
    for name in FILES.values():
        (directory / name).rename(target / name)
    (data / "dataset.jsonl").write_text("synthetic input\n")
    (data / "manifest.json").write_text("{}")
    monkeypatch.setattr(
        freeze_command,
        "load_snapshot",
        lambda *_: (rows, {"content_sha256": "synthetic-fingerprint", "taxonomy_version": "v2"}),
    )
    return data, rows, manifest


def test_freeze_preserves_reviews_and_assignments_and_is_idempotent(reviewed_bundle):
    data, rows, manifest = reviewed_bundle
    directory = data / "benchmark"
    before = fingerprint(directory)
    backup = data.parent / "backups"
    preview = freeze_command.freeze_benchmark(data, backup, "Reviewer", expected_groups=1)
    assert preview["status"] == "ready_to_freeze"
    assert fingerprint(directory) == before
    assert not backup.exists()
    result = freeze_command.freeze_benchmark(
        data, backup, "Reviewer", expected_groups=1, write=True
    )
    assert result["status"] == "frozen"
    saved = load_benchmark(directory, rows, "synthetic-fingerprint")
    assert saved.manifest["assignments"] == manifest["assignments"]
    for name, digest in before.items():
        if name != "split-manifest.json":
            assert fingerprint(directory)[name] == digest
    after = fingerprint(directory)
    assert (
        freeze_command.freeze_benchmark(data, backup, "Reviewer", expected_groups=1, write=True)[
            "status"
        ]
        == "already_frozen"
    )
    assert fingerprint(directory) == after
    assert len(list(backup.glob("*.json"))) == 1


@pytest.mark.parametrize("decision", ["", "unclear", "separate events"])
def test_unresolved_decision_cannot_be_frozen(reviewed_bundle, decision):
    data, _, _ = reviewed_bundle
    path = data / "benchmark/group-review.csv"
    fields, records = read_csv(path)
    records[0]["decision"] = decision
    write_csv(path, fields, records)
    before = fingerprint(data / "benchmark")
    with pytest.raises(ValueError, match="Every group decision"):
        freeze_command.freeze_benchmark(
            data, data.parent / "backups", "Reviewer", expected_groups=1, write=True
        )
    assert fingerprint(data / "benchmark") == before


def test_missing_review_blocks_freeze(reviewed_bundle):
    data, _, _ = reviewed_bundle
    with pytest.raises(ValueError, match="Expected 29"):
        freeze_command.freeze_benchmark(data, data.parent / "backups", "Reviewer", write=True)


def test_frozen_membership_change_is_detected(reviewed_bundle):
    data, rows, _ = reviewed_bundle
    freeze_command.freeze_benchmark(
        data, data.parent / "backups", "Reviewer", expected_groups=1, write=True
    )
    path = data / "benchmark/split-manifest.json"
    manifest = json.loads(path.read_text())
    reviewed_group = read_csv(data / "benchmark/group-review.csv")[1][0]["group_id"]
    group = next(
        item["group_id"] for item in manifest["assignments"] if item["group_id"] != reviewed_group
    )
    for item in manifest["assignments"]:
        if item["group_id"] == group:
            item["group_id"] = "changed-group"
    write_json(path, manifest)
    with pytest.raises(ValueError, match="Frozen split membership changed"):
        load_benchmark(data / "benchmark", rows, "synthetic-fingerprint")


def test_display_title_can_change_but_frozen_decision_cannot(reviewed_bundle):
    data, rows, _ = reviewed_bundle
    freeze_command.freeze_benchmark(
        data, data.parent / "backups", "Reviewer", expected_groups=1, write=True
    )
    path = data / "benchmark/group-review.csv"
    fields, records = read_csv(path)
    records[0]["preferred_title"] = "A clearer display label"
    write_csv(path, fields, records, delimiter=";")
    load_benchmark(data / "benchmark", rows, "synthetic-fingerprint")
    records[0]["decision"] = "unclear"
    write_csv(path, fields, records)
    with pytest.raises(ValueError, match="Every group decision"):
        load_benchmark(data / "benchmark", rows, "synthetic-fingerprint")
