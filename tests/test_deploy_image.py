"""Image deployment keeps the journal and refuses unsafe replacements."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "1" * 40
IMAGE = "ghcr.io/demo-radar/demo-radar-logic@sha256:" + "a" * 64
DOCKER = """import json, os, sys
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as out: out.write(json.dumps(args) + '\\n')
if args[:2] == ['image', 'inspect']:
    print('linux/' + os.environ.get('ARCH', 'arm64') + '|' + os.environ.get('IMAGE_COMMIT', os.environ['COMMIT']))
elif args[0] == 'inspect':
    if '.Mounts' in args[2]: print('true|volume|' + os.environ.get('JOURNAL_VOLUME', os.environ['LOGIC_PROJECT'] + '_inference-state'))
    else: print('previous-ref|old-id')
elif args[0] == 'compose' and 'ps' in args:
    if not os.environ.get('MISSING_SERVICE'): print('existing-logic')
elif args[:2] == ['exec', '-i'] and args[-1] == 'pause' and os.environ.get('UNRESOLVED'): sys.exit(1)
elif args[0] == 'cp':
    if os.environ.get('BACKUP_FAILURE'): sys.exit(1)
    from pathlib import Path
    folder=Path(args[-1]);folder.mkdir(parents=True)
    (folder / 'inference.sqlite').write_bytes(b'' if os.environ.get('EMPTY_BACKUP') else b'synthetic journal')
elif args[0] == 'compose' and 'exec' in args and os.environ.get('HEALTH_FAILURE'): sys.exit(1)
"""


@pytest.fixture
def deployment(tmp_path):
    (tmp_path / "scripts/deploy").mkdir(parents=True)
    for name in ("image.sh", "state.py"):
        shutil.copy(ROOT / "scripts/deploy" / name, tmp_path / "scripts/deploy" / name)
    docker = tmp_path / "docker"
    docker.write_text(f"#!{sys.executable}\n" + DOCKER)
    docker.chmod(0o700)
    calls = tmp_path / "calls.jsonl"

    def run(mode="--check", image=IMAGE, **env):
        return subprocess.run(
            ["bash", str(tmp_path / "scripts/deploy/image.sh"), mode, image, COMMIT],
            env={
                **os.environ,
                "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
                "LOGIC_PROJECT": "demologic-staging",
                "RADAR_DIR": str(tmp_path / "radar"),
                "DEMO_RADAR_NETWORK": "demo-radar-staging_default",
                "DEPLOYMENT_ENV": "staging",
                "COMMIT": COMMIT,
                "CALLS": str(calls),
                **env,
            },
            check=False,
            capture_output=True,
            text=True,
        )

    def commands():
        return [json.loads(x) for x in calls.read_text().splitlines()] if calls.exists() else []

    return run, commands, tmp_path


def test_check_only_pulls_and_validates(deployment):
    run, commands, _ = deployment
    result = run()
    assert result.returncode == 0, result.stderr
    assert any("pull" in x for x in commands())
    assert not any("stop" in x or "up" in x or "pause" in x for x in commands())


@pytest.mark.parametrize(
    "env", [{"ARCH": "amd64"}, {"IMAGE_COMMIT": "2" * 40}, {"MISSING_SERVICE": "1"}]
)
def test_invalid_image_or_missing_service_cannot_stop(deployment, env):
    run, commands, _ = deployment
    assert run("--apply", **env).returncode != 0
    assert not any("stop" in x or "up" in x for x in commands())


def test_tags_rejected_before_docker(deployment):
    run, commands, _ = deployment
    assert run(image="demologic:latest").returncode != 0
    assert commands() == []


def test_unknown_attempt_prevents_stop_and_replacement(deployment):
    run, commands, _ = deployment
    assert run("--apply", UNRESOLVED="1").returncode != 0
    assert not any("stop" in x or "up" in x for x in commands())


def test_backup_failure_leaves_old_container_stopped_without_replacement(deployment):
    run, commands, _ = deployment
    assert run("--apply", BACKUP_FAILURE="1").returncode != 0
    assert any(x[0] == "stop" for x in commands())
    assert not any("up" in x for x in commands())


def test_apply_preserves_journal_and_leaves_admission_paused(deployment):
    run, commands, root = deployment
    result = run("--apply")
    assert result.returncode == 0, result.stderr
    calls = commands()
    backup = next(i for i, x in enumerate(calls) if x[0] == "cp")
    restart = next(i for i, x in enumerate(calls) if "up" in x)
    assert backup < restart
    assert calls[backup][1].endswith(":/app/data/service/.")
    assert "--no-build" in calls[restart] and "--no-deps" in calls[restart]
    assert "--pull" in calls[restart] and "never" in calls[restart]
    assert "paused" in result.stdout
    assert list((root / "data/releases").glob("*/previous-image.txt"))
    assert not (root / "data/releases/deployment.lock").exists()
    assert IMAGE in (root / "data/releases/current-image.env").read_text()


def test_failed_readiness_and_concurrent_deploy_are_reported(deployment):
    run, _, root = deployment
    lock = root / "data/releases/deployment.lock"
    lock.mkdir(parents=True)
    assert run("--apply").returncode != 0
    lock.rmdir()
    assert run("--apply", HEALTH_FAILURE="1").returncode != 0


def test_wrong_journal_volume_cannot_pause_or_stop(deployment):
    run, commands, _ = deployment
    assert run("--apply", JOURNAL_VOLUME="new_empty_volume").returncode != 0
    assert not any("stop" in x or "up" in x or "pause" in x for x in commands())


def test_pause_drains_without_stopping_or_replacing(deployment):
    run, commands, _ = deployment
    result = run("--pause")
    assert result.returncode == 0, result.stderr
    assert any(x[-1] == "pause" for x in commands())
    assert not any("stop" in x or "up" in x for x in commands())


def test_empty_journal_backup_cannot_replace_container(deployment):
    run, commands, _ = deployment
    assert run("--apply", EMPTY_BACKUP="1").returncode != 0
    assert not any("up" in x for x in commands())
