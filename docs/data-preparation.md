# Preparing the private tagging dataset

This guide explains how DemoLogic gets its first dataset and why the data is kept outside Git. It is for a contributor who has not worked on either project before. The [ADR](adr/0001-capstone-backoffice-ml-vs-llm.md) explains the research plan; this page covers the practical handoff from the running application to the capstone.

## Where the data and code live

There are **two repositories**:

| Repository | Role |
|---|---|
| **Demo Radar** (`demo-radar`) | The existing application and production database. Its backend owns the read-only exporter, `backend.tagging_dataset_export`. Run that command in the Demo Radar deployment, with access to the intended database. |
| **DemoLogic** (`demo-radar-logic`) | The capstone project. Its `scripts/prepare_dataset.py` reads the export and creates the smaller private dataset used by notebooks and, later, model training. The production database is not accessed by the notebooks. |

The exporter is **not** part of this repository.
Access to production is for an authorized operator; other contributors can work from a privately shared prepared snapshot or the [public synthetic workflow](reproducibility.md).
> Do not try to run `python -m backend.tagging_dataset_export` from DemoLogic.


The source is a snapshot of Demo Radar demonstrations and their existing approved topic tags. Those tags are useful historical **training labels**, but some may be wrong. A separately reviewed sample will provide reference labels for the final comparison. The converter does not correct or independently verify a tag.

## What the files mean

`JSONL` means one JSON object per line. It can contain German text and Unicode characters. A *manifest* is a small JSON record of the export's version, row count, and SHA-256 fingerprint. The fingerprint lets us check that the bytes received by DemoLogic are exactly the bytes the exporter described.

| Private local file | Created by | Purpose |
|---|---|---|
| Source `dataset.jsonl` | Demo Radar exporter | Full export stream. It includes fields, such as tag assignment provenance, that DemoLogic does not need. It can stay on the source host and be streamed into the converter. |
| `data/source-manifest.json` | Demo Radar exporter, then copied locally | Describes the source stream. Keep it so the conversion can verify the row count and hash. |
| `data/dataset.jsonl` | DemoLogic converter | Prepared rows for the capstone. It contains labeled, active, dated demonstrations and the agreed input fields. |
| `data/manifest.json` | DemoLogic converter | Prepared row count, exclusions, tag counts, source identity, and fingerprint of the prepared file. |

As of **23 September 2026**, the deployed production exporter produces **source schema v1 / taxonomy v1**. The DemoLogic converter produces **prepared schema v2 / taxonomy v1**. Source and prepared schema numbers describe different files. The Demo Radar repository may already contain a newer exporter than the deployed one, so check the manifest from the deployment rather than assuming the checked-out code describes today's production export.

The prepared taxonomy-v2 change replaces `conflict` with `international-politics`. The converter now accepts source schemas 1 and 2 with declared taxonomy v1 or v2; it does not silently migrate labels. Existing v1 snapshots remain valid. Use the [separate-copy migration](taxonomy-migration.md) when moving an existing reviewed benchmark to v2.

## Reproduce a snapshot

1. **Export from Demo Radar.** In the Demo Radar deployment, run its read-only `backend.tagging_dataset_export` against the database you intend to study. For the historical production v1 exporter recorded above, pass `--skip-migrations`, `--source-environment production`, and the full Git revision of the deployed exporter. Choose a temporary output directory accessible only to the operator. Do not pass `--include-deleted` for the main benchmark. Record the export time and deployed revision. The exact command depends on the deployment. Run the exporter inside the intended Demo Radar backend container, not on the SSH client.
2. **Copy the small manifest privately.** If the exporter wrote it inside the backend container, first copy it to a private path on the server host. Then, from the DemoLogic repository root, use `scp` to bring it to your machine (replace `user@source-host` and the example server path with the actual values):

   ```bash
   umask 077
   mkdir -p data
   export DEMO_SOURCE=user@source-host
   scp "${DEMO_SOURCE}:/private/path/on/server/manifest.json" data/source-manifest.json
   chmod 600 data/source-manifest.json
   ```

   Check that `data/source-manifest.json` declares a supported source schema (v1 or v2), a supported taxonomy (v1 or v2), and `source_environment: production`. Keep the version values supplied by the exporter; editing the manifest does not migrate the data. The `data/` directory is Git-ignored; keep its files accessible only to your local user account. `scp` reads files on the server host, not files that exist only inside a Docker container.

3. **Convert the source stream.** From the DemoLogic repository root, pipe the export's `dataset.jsonl` into the converter. Here is the command when the source JSONL is already available in a private local file; a stream sent over SSH works in place of `cat` as well:

   ```bash
   set -o pipefail
   cat /private/path/to/source-dataset.jsonl | \
     uv run --locked python scripts/prepare_dataset.py \
       --source-manifest data/source-manifest.json \
       --output-dir data/
   ```

   `set -o pipefail` makes the command fail if reading the source fails, even if the converter process exits normally. The converter checks the source row count and SHA-256 fingerprint **before writing** its prepared files. It also rejects unexpected schema fields, event IDs, lifecycle values, and topic tags rather than silently accepting a changed export. If the exporter changes, update the converter and its tests before generating a new benchmark snapshot.
4. **Review the resulting summary without publishing rows.** Inspect `data/manifest.json` for source and prepared counts, excluded untagged/deleted/undated records, tag frequencies, and missing-field counts. Confirm that `data/dataset.jsonl` is present and its SHA-256 matches `content_sha256` in the prepared manifest. Record the DemoLogic conversion revision alongside the source revision and hashes. The first notebook, `01_data_snapshot_and_quality.ipynb`, will perform the broader quality review; the next notebook examines repeated events and validates the saved evaluation split.
5. **Remove unnecessary raw copies and check Git.** Once conversion and verification succeed, remove any temporary source JSONL copies from the source host and local machine according to the project's retention policy. Before pushing, run `uv run --locked python scripts/check_public_repo.py` and inspect `git status`. Real exports, reviewed labels, row-level predictions, and fitted private artifacts must not be committed or baked into a Docker image.

The converter drops untagged, deleted, and undated rows and removes assignment provenance. It keeps the original title text. JSON escapes such as `\u00d6` are decoded when read and written as UTF-8; strings such as `&#703;`, unusual spacing, and split words are retained. Whether to decode entities or repair text for a model is a separate, documented feature-preparation experiment. Keep raw and cleaned text distinguishable so the source record and its hash remain traceable.

## Restore the private benchmark

The prepared source remains at `data/dataset.jsonl` with `data/manifest.json`.
The one active benchmark candidate and its private review files are under
`data/benchmark/`. Notebook 02 reads the saved split and completed reviews there;
it does not create another candidate each time it runs. The benchmark manifest
records the selected split settings and source fingerprint. A pending status
means group decisions still need verification; `frozen` means the saved membership
and reviewed decisions have been recorded and are checked whenever the bundle is loaded.
Keep these files out of Git, including completed review notes and labels.

For a new checkout, ask an authorized project maintainer for the prepared snapshot (`data/dataset.jsonl` and `data/manifest.json`) and its complete benchmark bundle. Copy the following five files into `data/benchmark/`, retaining their names:

| File | What it preserves |
|---|---|
| `split-manifest.json` | Saved event-to-split assignments, grouping policy, selection settings, and snapshot fingerprint |
| `group-review.csv` | Reviewed event-type groups, reviewer decisions, and optional readable labels in `preferred_title` |
| `rubric-pilot-queue.csv` | The 40 pilot records and any completed labels or notes |
| `rubric-pilot-selection.json` | Pilot selection IDs, snapshot fingerprint, and split seed |
| `final-review-queue.csv` | The records reserved for final reference-label review |

The final-review queue is the separate answer-key task. Its optional `title_en` column contains Codex translations of the original `title`, added on 28 September 2026 as a reading aid for the reviewer. The original text remains authoritative; unclear words and source truncation should be checked against it. Translations do not assign tags and are not model features or few-shot examples. Keep the added column when sharing the review file privately. Do not fill reference labels from historical assignments or notebook predictions. Use approved rubric-v1 with taxonomy v2; see the [comparison stages](methodology.md#comparison-stages) for study context and the bundle checks below for restoration requirements.

Transfer these files privately, for example with `scp`, and restrict access to your user account. Preserve completed reviews before replacing any local files. Do not mix files from different candidate splits: the same source snapshot can have more than one split.

Follow the [notebook setup guide](notebook-setup.md), then run notebook 02 from the beginning. Its loader checks eligible event IDs, split membership, saved counts and selection limits, and the IDs in the review files. Group-review dates may use ISO (`2026-09-23`) or German spreadsheet formatting (`23.09.2026` or `23.09.26`); the loader compares them with the expected snapshot date without editing the CSV. Missing or inconsistent files produce an error with recovery guidance; the notebook does not repair or overwrite them.

Review the 29 group-review rows as distinct event types. A type may have several dated occurrences sharing a name, organizer, and label. The prepared snapshot does not independently record the organizer, so this is a review decision rather than a field the loader can verify. Keeping occurrences of one type in the same split prevents repeated editions from appearing on both sides of a model evaluation; it does not merge or delete the occurrences.

`title_variants` contains normalized text used to find related records. `preferred_title` is a short, human-readable label for that event type, including groups with only one title variant. It may be edited for clarity and does not need to match an original source title. The benchmark loader checks group IDs, counts, and dates, but does not treat this display label as evidence. Each occurrence retains its original title as model input. Replacing model input with a group label would be a separate feature experiment.

The active candidate was originally selected with grouping policy v1. The two-word title rule was then applied to those saved assignments without redrawing the split. Restoring this bundle reproduces that saved decision. Running the current grouping and selection code would create a new candidate and may choose different records; that requires an explicit reconciliation of existing reviews, not a routine notebook rerun.


## Freeze reviewed split membership

After the group review is complete, replace `<reviewer-id>` with the identifier
of the person who approved the grouping. Keep the quotes so an identifier with
spaces is passed as one argument. It is saved in the private freeze record for
accountability; do not use the literal placeholder as a reviewer name.

Preview the checks from the repository root:

```bash
uv run --locked python scripts/freeze_benchmark.py --reviewer "<reviewer-id>"
```

The current task expects 29 reviewed event types, each marked `same event`. The command validates the complete bundle, including counts, group dates, 40 pilot records in validation, and every final-review record in final test. It keeps the current assignments. A blank, unclear or separate-events decision stops the freeze and needs reconciliation; the command does not invent a new grouping.

To save the verified freeze:

```bash
uv run --locked python scripts/freeze_benchmark.py --reviewer "<reviewer-id>" --write
```

Only `split-manifest.json` is updated. It records `status: frozen`, the timestamp, reviewer, reviewed group/occurrence counts, and fingerprints of membership and decisions. The original manifest is retained privately under `artifacts/split-freeze-backups/` for recovery. It is not a second active candidate. Repeating the command on a verified frozen bundle changes nothing.

Reload notebook 02 from disk, restart the Jupyter kernel, and run all cells. In **section 1**, the **Benchmark fact** table should show **Split membership: locked** and **Reviewed event types: 29**. In **section 6**, check **2,626 training**, **659 validation**, and **149 final-test** records. These are the DR-34 review locations; no repeat CSV review is required.

### Count recurring event types once (DR-40)

The counts above describe source occurrences. For the main model comparison,
Notebooks 03 and 04 select **732 training, 188 validation and 123 final-test
representatives**, one per saved group. The locked split and all original reviews
remain intact. Reload the notebooks from disk and restart the kernel before rerunning.

Selection uses the earliest date, with the event ID breaking ties. The 40 validation
pilot groups retain their already-selected review records. Tags and model results
never choose a representative. A selected record keeps its original title and
historical tags, even when other editions have different titles or assignments.
These disagreements remain a label-quality limitation, not a reason to invent a
combined answer. Reviewer-supplied final labels are joined only when final evaluation is ready.

Both modeling notebooks save the same private `data/benchmark/event-type-representatives-v1.json`.
It records each selected ID, all group member IDs, the policy version and a fingerprint.
If the file differs from a newly computed selection, saving stops: investigate and
version a deliberate change rather than overwrite it. Report comparisons require
matching selection fingerprints. Earlier occurrence-based reports remain available
but cannot serve as the matching baseline for this new experiment.

The separate repeat-history simulation in Notebook 03 still uses all validation
occurrences, because it tests reuse of earlier tags. Its scores are supplementary.

“Locked” is the notebook's readable name for the internal `status: frozen`. These assignments are fixed for the model comparison. Label review can continue. Changing which demonstrations belong to each split requires a new recorded split version. The files are not made read-only; the loader detects changes against the saved membership and group decisions. Readable group titles and later reference-label edits do not change membership. The source snapshot does not independently verify organizers; the recorded grouping follows the reviewer’s recorded decision.

## Record private audit decisions

Keep **one local audit file per calendar day**: `reports/YYYY-MM-DD.md` (Berlin date). Put each task under its own heading in that day's file, for example “Export and prepare the dataset” and “Group events and reserve a candidate split.” For each task, record the input snapshot, checks performed, findings, decision, unresolved questions, and next action. If a decision changes later that day, append a dated correction so the earlier reason remains visible. On a new day, create a new file and link back to the decision it revises.

The audit records the reviewer’s explanation of the work; manifests remain the machine-readable record of hashes, versions, and split assignments. `reports/` is Git-ignored because these notes may refer to private data. The first daily record is `reports/2026-09-23.md`; do not create separate data-audit and split-audit files for the same date.

## Why the preparation step is a script

The export-to-dataset conversion must produce the same bytes every time and stop on an invalid export. A small tested script is easier to rerun, use in a private pipeline, and audit than a notebook with cells that might be executed out of order. The script contains no exploratory analysis and prints only a summary, not demonstration text.

Notebooks are still central to the project. `01_data_snapshot_and_quality.ipynb` reads the prepared local dataset, examines data quality, and records the inclusion decision. `02_label_audit_eda_and_splits.ipynb` inspects labels and recurring events and validates the saved benchmark split. Later notebooks compare models. They should call the same tested package code when a step needs to be repeatable; they should not each implement a different export converter. Clear private row outputs before committing notebooks.
