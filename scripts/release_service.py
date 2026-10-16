"""Verify an ARM64 service image, then publish it without rebuilding."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EVIDENCE = Path("release-evidence")
MANIFEST = EVIDENCE / "release.json"


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def image_identity(image, commit):
    value = command(
        "docker",
        "image",
        "inspect",
        "--format",
        '{{.Id}}|{{.Os}}|{{.Architecture}}|{{index .Config.Labels "org.opencontainers.image.revision"}}',
        image,
    )
    identity, system, architecture, revision = value.split("|")
    if (system, architecture, revision) != ("linux", "arm64", commit):
        raise ValueError("Image must be linux/arm64 and labelled with this source commit")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
        raise ValueError("Invalid image identity")
    return identity


def log_hash():
    return hashlib.sha256((EVIDENCE / "smoke.log").read_bytes()).hexdigest()


def save(data):
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n")


def verify(image):
    commit = command("git", "rev-parse", "HEAD")
    identity = image_identity(image, commit)
    EVIDENCE.mkdir(mode=0o700, exist_ok=True)
    # A failed rerun must not leave an earlier successful verification behind.
    MANIFEST.unlink(missing_ok=True)
    result = subprocess.run(
        [sys.executable, "scripts/smoke_service.py", image],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (EVIDENCE / "smoke.log").write_text(result.stdout)
    print(result.stdout, end="")
    result.check_returncode()
    if image_identity(image, commit) != identity:
        raise ValueError("Image changed during verification")
    save(
        {
            "schema_version": 1,
            "source_commit": commit,
            "source_dirty": bool(command("git", "status", "--porcelain")),
            "platform": "linux/arm64",
            "image": image,
            "image_id": identity,
            "smoke_log_sha256": log_hash(),
            "workflow_run": os.environ.get("GITHUB_RUN_ID"),
            "verification": "offline API, auth, tag and summary replay, maintenance and restart",
        }
    )


def registry_matches(target, manifest, expected):
    if manifest.get("config", {}).get("digest") == expected:
        return True
    # Containerd reports the manifest or provenance index as the local image ID.
    digest = command(
        "docker", "buildx", "imagetools", "inspect", target, "--format", "{{.Manifest.Digest}}"
    )
    return digest == expected


def publish():
    data = json.loads(MANIFEST.read_text())
    commit = command("git", "rev-parse", "HEAD")
    if (
        os.environ.get("GITHUB_REF") != "refs/heads/main"
        or data["source_dirty"]
        or command("git", "status", "--porcelain")
        or data["source_commit"] != commit
    ):
        raise ValueError("Publish only a clean, tested main checkout")
    if log_hash() != data["smoke_log_sha256"]:
        raise ValueError("Smoke evidence changed after verification")
    if image_identity(data["image"], commit) != data["image_id"]:
        raise ValueError("Image changed after verification")
    repository = os.environ["GITHUB_REPOSITORY"].lower()
    if not re.fullmatch(r"[a-z0-9-]+/demo-radar-logic", repository):
        raise ValueError("Unexpected GHCR repository")
    target = f"ghcr.io/{repository}:sha-{commit}"
    existing = subprocess.run(
        ["docker", "manifest", "inspect", target], capture_output=True, text=True, check=False
    )
    if existing.returncode == 0:
        if not registry_matches(target, json.loads(existing.stdout), data["image_id"]):
            raise ValueError("Refusing to overwrite an existing commit tag")
        subprocess.run(["docker", "pull", target], check=True)
    elif not re.search(
        r"manifest unknown|no such manifest|name unknown", existing.stderr, re.IGNORECASE
    ):
        raise RuntimeError(existing.stderr)
    else:
        subprocess.run(["docker", "tag", data["image"], target], check=True)
        subprocess.run(["docker", "push", target], check=True)
    remote = json.loads(command("docker", "manifest", "inspect", target))
    if not registry_matches(target, remote, data["image_id"]):
        raise ValueError("Registry image differs from the tested image")
    digests = command(
        "docker",
        "image",
        "inspect",
        "--format",
        "{{range .RepoDigests}}{{println .}}{{end}}",
        target,
    ).splitlines()
    prefix = target.rsplit(":", 1)[0] + "@"
    refs = [ref for ref in digests if ref.startswith(prefix)]
    if len(refs) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", refs[0][len(prefix) :]):
        raise ValueError("Registry digest missing")
    data.update({"tag": target, "registry_ref": refs[0]})
    save(data)
    print(f"Published tested image: {refs[0]}")


if __name__ == "__main__":
    os.umask(0o077)
    if sys.argv[1:] == ["publish"]:
        publish()
    elif len(sys.argv) == 3 and sys.argv[1] == "verify":
        verify(sys.argv[2])
    else:
        raise SystemExit("Usage: release_service.py verify IMAGE | publish")
