"""Exercise publication checks in temporary repositories with synthetic files."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECK_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_public_repo.py"


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Create an isolated Git index without touching the project's staged files."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def stage(repository: Path, name: str, content: str = "synthetic") -> Path:
    """Write and stage a synthetic file, including ignored-looking filenames."""
    path = repository / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "--", name], cwd=repository, check=True)
    return path


def run_check(repository: Path) -> subprocess.CompletedProcess:
    """Run the real command against the temporary repository's index."""
    return subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("name", ["data/private.json", "data/ä.json", "data/a\nb.json", ".env"])
def test_private_paths_are_rejected(repository: Path, name: str) -> None:
    stage(repository, name)
    result = run_check(repository)
    assert result.returncode == 1
    assert "is tracked" in result.stdout or "private directory" in result.stdout


def test_public_placeholders_and_synthetic_data_are_allowed(repository: Path) -> None:
    for name in ("data/.gitkeep", ".env.example", "examples/synthetic/events.csv"):
        stage(repository, name)
    assert run_check(repository).returncode == 0


def test_notebook_check_reads_staged_content_in_any_directory(repository: Path) -> None:
    saved = {"cells": [{"cell_type": "code", "outputs": ["synthetic"], "execution_count": 1}]}
    path = stage(repository, "experiments/check.ipynb", json.dumps(saved))
    path.write_text(json.dumps({"cells": []}), encoding="utf-8")
    result = run_check(repository)
    assert result.returncode == 1
    assert "saved output" in result.stdout
    subprocess.run(["git", "add", "--", str(path)], cwd=repository, check=True)
    assert run_check(repository).returncode == 0


@pytest.mark.parametrize("content", ["not JSON", "[]", '{"cells": [null]}'])
def test_invalid_notebooks_report_errors_without_tracebacks(repository: Path, content: str) -> None:
    stage(repository, "invalid.ipynb", content)
    result = run_check(repository)
    assert result.returncode == 1
    assert "invalid notebook" in result.stdout
    assert "Traceback" not in result.stderr
