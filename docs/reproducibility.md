# Reproduce the public example

This workflow checks DemoLogic’s software with invented inputs. It does not
reproduce the private benchmark scores or measure a real model’s quality.
No Demo Radar export, reviewed answer key, provider key or paid call is needed.

## Clean setup

Use a fresh checkout of the revision you want to review. Do not copy `.env`,
`service/.env`, `.venv`, `data`, `reports` or `artifacts` from another checkout.
Install Python through uv using the committed `.python-version` and `uv.lock`.

```bash
git clone https://github.com/demo-radar/demo-radar-logic.git demo-logic-check
cd demo-logic-check
git rev-parse HEAD
uv python install
uv sync --locked --group notebooks --group service
uv run --locked ruff check src scripts tests service notebooks/tools
uv run --locked ruff format --check src scripts tests service notebooks/tools
uv run --locked python scripts/check_public_repo.py
uv run --locked --group notebooks --group service pytest -q
```

For a particular published release, check out its recorded revision before the
setup steps. Record the displayed commit ID with your check results. A private
repository requires Git access; access does not grant access to the private dataset. The first installation downloads dependencies.
The tests use synthetic inputs and mocked transports, not provider credentials.
The semantic model weights and an external Jupyter Compose file are not
needed for these checks.

The suite checks conversion and source hashes, grouped split isolation,
evaluation arithmetic, notebook experiment definitions, API contracts, saved
answers, daily drafts and recovery. Temporary test files are created outside
the private dataset. A green suite verifies these examples and failure paths;
it is not a new experiment result.

## Synthetic API walkthrough

Docker must be running. From the same clean checkout:

```bash
docker build -t demologic:reproduction .
python3 scripts/smoke_service.py demologic:reproduction
```

The script creates its own token, container and journal volume. It never reads
`.env` and removes only the resources it created. Expected output:

```text
Docker smoke check passed: auth, synthetic tags/daily draft, replay and maintenance restart.
No provider requests or .env access.
```

The tag request is represented by [the invented public example](../examples/synthetic/tag-request.json).
The [smoke script](../scripts/smoke_service.py) also builds an invented daily
snapshot. It checks unauthorized access, a mobility suggestion, a private daily
draft, replay without a new call, maintenance persistence across restart and
resumption. Demo mode is a software fixture; its answer is not a Qwen prediction.
For manual curl steps, use the [service guide](service-api.md).

## Research results and limits

Public notebooks retain their code and Markdown, with outputs cleared. Running
the experiments in full requires authorized private inputs and, for live runs,
separate provider approval. Follow [data preparation](data-preparation.md) and
[notebook setup](notebook-setup.md); do not substitute synthetic rows for the
private benchmark and claim the published scores were reproduced.

The [original final comparison](plan/final-evaluation.md) and
[fresh v4 confirmation](results/fresh-v4-confirmation.md) record aggregate
results and their sample sizes. Original final results, repeatedly reviewed
development cases and the later fresh check remain separate. The reviewer was the sole
reviewer; the fresh check is not independent second-reviewer evidence.
No candidate met all original quality targets together. Reviewer approval remains
required, and measured production time savings remain unverified.

Trace source hashes, split membership, reference/rubric versions, model settings
and saved predictions through each notebook’s configuration and private report.
Public service catalogs pin configuration hashes; tests verify the selected
configuration and rubric contract. Aggregate tables cannot recreate omitted
row-level predictions. Retain the private evidence rather than publishing it.

## Publication boundary

Review the exact files prepared for the public release. Earlier private commits
belong in the separate research archive, not in the public snapshot.
The [publication checker](../scripts/check_public_repo.py) checks Git’s index for
common private paths and saved notebook outputs. It does not scan arbitrary
text for secrets, review images or prove old commits safe.

Keep private snapshots, reference labels, review packets, responses, journals,
fitted artifacts and runtime settings out of the package and Docker context.
Use invented examples and reviewed aggregate charts. Inspect screenshots,
speaker notes and embedded spreadsheets before sharing a deck. Keep generated
exports under ignored `artifacts/presentations/`. Retired exports and earlier
commits are preserved in the private research archive.

Internal publication evidence is maintained in the project’s issue tracker.
Use [research replay](research-replay.md) for original experiment inputs and
[security reporting](../SECURITY.md) for sensitive concerns. The public workflow
does not reproduce private benchmark scores or certify that every historical
object or third-party asset is safe to distribute.
