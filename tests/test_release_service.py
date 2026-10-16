"""Release verification must finish before an unchanged image can be published."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "release_service", Path(__file__).resolve().parents[1] / "scripts/release_service.py"
)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
COMMIT = "1" * 40
IMAGE_ID = "sha256:" + "a" * 64


@pytest.fixture
def commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_REPOSITORY", "demo-radar/demo-radar-logic")
    state = {
        "calls": [],
        "dirty": "",
        "id": IMAGE_ID,
        "arch": "arm64",
        "smoke": 0,
        "pushed": False,
        "conflict": False,
        "down": False,
        "existing": False,
        "index": False,
        "remote_id": IMAGE_ID,
    }

    def command(*args):
        state["calls"].append(args)
        if args[:2] == ("git", "rev-parse"):
            return COMMIT
        if args[:2] == ("git", "status"):
            return state["dirty"]
        if args[:3] == ("docker", "image", "inspect"):
            if "RepoDigests" in args[4]:
                return "ghcr.io/demo-radar/demo-radar-logic@sha256:" + "b" * 64
            return f"{state['id']}|linux|{state['arch']}|{COMMIT}"
        if args[:3] == ("docker", "buildx", "imagetools"):
            return "different" if state["conflict"] else state["remote_id"]
        if args[:3] == ("docker", "manifest", "inspect"):
            if state["index"]:
                return json.dumps({"manifests": []})
            return json.dumps({"config": {"digest": state["id"]}})
        raise AssertionError(args)

    def run(args, **kwargs):
        state["calls"].append(tuple(args))
        if "smoke_service.py" in args[1]:
            return subprocess.CompletedProcess(args, state["smoke"], stdout="synthetic smoke")
        if args[:3] == ["docker", "manifest", "inspect"]:
            if state["down"]:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="connection refused")
            if state["index"] and (state["existing"] or state["conflict"]):
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"manifests": []}))
            if state.get("existing"):
                return subprocess.CompletedProcess(
                    args, 0, stdout=json.dumps({"config": {"digest": IMAGE_ID}})
                )
            if state["conflict"]:
                return subprocess.CompletedProcess(
                    args, 0, stdout=json.dumps({"config": {"digest": "different"}})
                )
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="manifest unknown")
        if args[:2] == ["docker", "push"]:
            state["pushed"] = True
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(release, "command", command)
    monkeypatch.setattr(release.subprocess, "run", run)
    return state


def test_verified_image_publishes_without_rebuild(commands):
    release.verify("demologic:candidate")
    release.publish()
    data = json.loads(release.MANIFEST.read_text())
    assert data["registry_ref"].startswith("ghcr.io/demo-radar/demo-radar-logic@sha256:")
    assert data["image_id"] == IMAGE_ID
    assert commands["pushed"]
    assert not any(call[:2] == ("docker", "build") for call in commands["calls"])


def test_failed_smoke_removes_previous_verification(commands):
    release.verify("demologic:candidate")
    commands["smoke"] = 1
    with pytest.raises(subprocess.CalledProcessError):
        release.verify("demologic:candidate")
    assert not release.MANIFEST.exists()
    assert not commands["pushed"]


def test_non_arm64_image_is_rejected_before_smoke(commands):
    commands["arch"] = "amd64"
    with pytest.raises(ValueError, match="linux/arm64"):
        release.verify("demologic:candidate")
    assert not commands["pushed"]


@pytest.mark.parametrize("dirty_at_verification", [False, True])
def test_dirty_source_cannot_be_published(commands, dirty_at_verification):
    commands["dirty"] = " M changed.py" if dirty_at_verification else ""
    release.verify("demologic:candidate")
    commands["dirty"] = "" if dirty_at_verification else " M changed.py"
    with pytest.raises(ValueError, match="clean, tested main"):
        release.publish()
    assert not commands["pushed"]


def test_feature_branch_cannot_publish(commands, monkeypatch):
    release.verify("demologic:candidate")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    with pytest.raises(ValueError, match="clean, tested main"):
        release.publish()
    assert not commands["pushed"]


def test_changed_image_cannot_publish(commands):
    release.verify("demologic:candidate")
    commands["id"] = "sha256:" + "c" * 64
    with pytest.raises(ValueError, match="Image changed"):
        release.publish()
    assert not commands["pushed"]


def test_changed_smoke_log_cannot_publish(commands):
    release.verify("demologic:candidate")
    (release.EVIDENCE / "smoke.log").write_text("changed")
    with pytest.raises(ValueError, match="Smoke evidence changed"):
        release.publish()
    assert not commands["pushed"]


def test_existing_commit_tag_and_registry_outage_cannot_publish(commands):
    release.verify("demologic:candidate")
    commands["conflict"] = True
    with pytest.raises(ValueError, match="overwrite"):
        release.publish()
    commands["conflict"] = False
    commands["down"] = True
    with pytest.raises(RuntimeError, match="connection refused"):
        release.publish()
    assert not commands["pushed"]


def test_matching_commit_tag_is_reused_without_a_push(commands):
    release.verify("demologic:candidate")
    commands["existing"] = True
    release.publish()
    assert not commands["pushed"]
    assert json.loads(release.MANIFEST.read_text())["registry_ref"]


@pytest.mark.parametrize("existing", [False, True])
def test_provenance_index_matches_tested_containerd_identity(commands, existing):
    commands["index"] = True
    commands["existing"] = existing
    release.verify("demologic:candidate")
    release.publish()
    assert commands["pushed"] is not existing
    assert json.loads(release.MANIFEST.read_text())["registry_ref"]


def test_different_provenance_index_cannot_replace_commit_tag(commands):
    commands["index"] = True
    commands["conflict"] = True
    release.verify("demologic:candidate")
    with pytest.raises(ValueError, match="overwrite"):
        release.publish()
    assert not commands["pushed"]


def test_changed_registry_index_is_rejected_after_push(commands):
    commands["index"] = True
    commands["remote_id"] = "sha256:" + "d" * 64
    release.verify("demologic:candidate")
    with pytest.raises(ValueError, match="differs"):
        release.publish()
