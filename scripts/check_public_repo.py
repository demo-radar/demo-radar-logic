"""Check that the files staged for commit are suitable for the public repository.

Run ``uv run --locked python scripts/check_public_repo.py`` from the repository
root before committing. The check reads Git's index: the version of each file
that would be included in the next commit, including already tracked files.

Report private files in data/, reports/, and artifacts/; data or model files
outside examples/synthetic/; and credential-like files such as .env or .pem.
The .gitkeep placeholders and .env.example are allowed. Every tracked notebook
is also checked for saved code-cell outputs and execution counts.

For example, if a notebook with outputs was staged and then cleared locally,
the check still reports its staged outputs. Stage the cleared version and run
the check again. Untracked files are not checked because Git will not publish
them in the next commit.

Exit with status 0 when these checks pass, or 1 after listing problems. This
check catches common publication mistakes; it does not inspect arbitrary text
for secrets or replace a human review of the staged changes.
"""

import json
import subprocess
from pathlib import Path

PRIVATE_DIRECTORIES = ("data/", "reports/", "artifacts/")
PRIVATE_SUFFIXES = {
    ".csv",
    ".jsonl",
    ".parquet",
    ".pkl",
    ".joblib",
    ".pt",
    ".onnx",
    ".safetensors",
    ".sqlite",
    ".db",
}


def tracked_paths() -> list[str]:
    """Read exact filenames, including Unicode and newlines, from Git's index."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="surrogateescape",
    )
    return [name for name in result.stdout.split("\0") if name]


def _path_problems(name: str) -> list[str]:
    """Check one tracked path for private data, model files, or credentials."""
    path = Path(name)
    problems = []
    if name.startswith(PRIVATE_DIRECTORIES) and path.name != ".gitkeep":
        problems.append(f"private directory contains tracked file: {name}")
    if path.suffix.lower() in PRIVATE_SUFFIXES and not name.startswith("examples/synthetic/"):
        problems.append(f"data or model artifact is tracked: {name}")
    if (
        path.name == ".env"
        or (path.name.startswith(".env.") and path.name != ".env.example")
        or path.suffix.lower() in {".pem", ".key"}
    ):
        problems.append(f"credential-shaped file is tracked: {name}")
    return problems


def _notebook_problems(name: str) -> list[str]:
    """Check the staged notebook, even when its working copy was cleared later."""
    try:
        result = subprocess.run(["git", "show", f":{name}"], check=True, capture_output=True)
        content = json.loads(result.stdout)
    except (subprocess.CalledProcessError, ValueError) as exc:
        return [f"invalid notebook {name}: {exc}"]
    if not isinstance(content, dict) or not isinstance(content.get("cells"), list):
        return [f"invalid notebook {name}: expected an object with a cells list"]
    problems = []
    for index, cell in enumerate(content["cells"], start=1):
        if not isinstance(cell, dict):
            problems.append(f"invalid notebook {name}, cell {index}: expected an object")
        elif cell.get("cell_type") == "code" and (
            cell.get("outputs") or cell.get("execution_count") is not None
        ):
            problems.append(f"saved output in {name}, cell {index}")
    return problems


def main() -> int:
    """Report publication problems in tracked files; return 1 if any are found.

    Check every tracked notebook, wherever it lives. Inspect Git's staged
    contents so clearing a local notebook cannot hide outputs already staged
    for commit. Untracked private experiments are outside this check.
    """
    problems = []
    for name in tracked_paths():
        problems.extend(_path_problems(name))
        if Path(name).suffix.lower() == ".ipynb":
            problems.extend(_notebook_problems(name))
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        return 1
    print("Public repository check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
