# Contributing

Start with the [project overview](README.md), [documentation index](docs/README.md)
and [public synthetic workflow](docs/reproducibility.md). Python 3.13 and the
committed lockfile define the development environment.

```bash
uv python install
uv sync --locked --group notebooks --group service
uv run --locked ruff check src scripts tests service notebooks/tools
uv run --locked ruff format --check src scripts tests service notebooks/tools
uv run --locked --group notebooks --group service pytest -q
uv run --locked python scripts/check_public_repo.py
```

Update `uv.lock` when dependencies change. Install the larger semantic group only
when working on the NLI experiment. Public tests use invented data and mocked
provider transports. They need no runtime `.env` or provider key.

## Research and implementation

Keep experiment selection, fitting and comparisons visible in notebook cells.
Share stable validation and metrics through `src/demo_logic/`; service code
belongs under `service/`. Use the [notebook index](notebooks/README.md) and
[historical replay guide](docs/research-replay.md) before running old experiments.

Keep source versions, reference versions and configuration fingerprints traceable.
Do not alter a saved answer key or weaken a hash check to improve a model’s score.
Changing a prompt, rubric or response contract requires versioning and relevant
contract tests. Preserve original comparisons when reporting a follow-up.

## Publication boundary

Use a topic branch and a pull request describing the problem, change and checks.
Keep notebook outputs and execution counts cleared. Public examples must be
invented or specifically reviewed for sharing. Inspect images, notes and embedded
files as well as ordinary text.

Private snapshots, reference labels, predictions, fitted artifacts, provider
responses, journals, review packets and credentials stay outside Git and Docker
builds. The publication checker reads the index; it is not a complete history,
secret or image-content audit. Internal work logs belong in the issue tracker.
Report sensitive findings through the [security contact](SECURITY.md).
