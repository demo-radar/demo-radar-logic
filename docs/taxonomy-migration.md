# Taxonomy v1 → v2

Status: migration implementation prepared. The local DemoLogic benchmark was activated on taxonomy v2 on 25 September 2026, with its original v1 bundle backed up privately. Production deployment is managed separately; local activation does not depend on it.

The automatic change is a rename map, defined in `src/demo_logic/taxonomy.py`:

```python
V1_TO_V2 = {"conflict": "international-politics"}
```

The new tag also covers foreign political affairs. `politics` now means German domestic politics. Healthcare access belongs under `social-issues`. There are still 12 topic tags.

## What happens automatically?

The migration translates only mapped tag tokens. It keeps event IDs, original titles, other features, group decisions, readable group labels, and train/validation/test assignments. It translates the same tag name in reviewed tags and per-tag uncertainty entries, preserving the scores and notes. It updates dataset fingerprints, tag counts, split metadata, and pilot-selection metadata together so the notebooks can still validate the complete bundle. File schema v2 and taxonomy v2 are separate concepts.

The map does not reclassify every `politics` row. Those rows need review because their previous meaning included more than German domestic politics. The broader international tag can also apply to foreign political issues previously tagged only as `human-rights`, `lgbtq`, or another topic. Review those definitions on development examples, then label the reserved final set independently under v2. Do not use model predictions to decide final-test answers. Old healthcare labels under `education` also need review.

## Prepare the private DemoLogic copy

From the DemoLogic repository, preview the impact:

```bash
uv run --locked python -m demo_logic.migrate_taxonomy \
  --source-dir data --output-dir artifacts/taxonomy-v2
```

This default dry run prints counts and hashes and creates no output. To prepare a separate copy:

```bash
uv run --locked python -m demo_logic.migrate_taxonomy \
  --source-dir data --output-dir artifacts/taxonomy-v2 --write
```

The destination must not exist and must be outside the source directory. Both `data/` and `artifacts/` are Git-ignored. Output files are owner-only. The old source remains untouched; the new bundle is validated before success is reported. The migration report marks semantic review as pending. The final-review queue remains blank if it was blank before.

Activation is a later operator step: after reviewing the output, archive the current private `data/` bundle outside Git and place the complete new bundle at the notebook's `data/` location. Do not mix individual files from old and new bundles. Re-run notebook 02. A taxonomy migration does not itself freeze the split or approve reference labels. Keep the old snapshot until old experiments no longer need to be reproduced.

## Prepare Demo Radar

Demo Radar's Alembic revision `0019_international_politics` contains the same frozen rename map. It creates/updates the new catalog definitions, translates assignments and topic memory in place, translates proposal slug references, and deactivates `conflict`. Assignment IDs, provenance, scores, and historical audit text are retained. A collision where both slugs already exist on one assignment or memory key stops the migration before changes; reconcile that data before retrying.

Deployment must stop writers and coordinate the code and database change. Demo Radar runs migrations at startup, so deploying this revision can apply it automatically. Review and back up the database before an explicitly approved deployment. No production command is run during capstone preparation.

There is no automatic semantic downgrade: after new international topics are labeled, converting them all back to conflict would be misleading. Recovery requires a pre-migration backup or a reviewed forward migration. Do not roll back a live database and discard later writes.

Legacy `conflict` imports are mapped to the replacement slug. Generic automatic `politics` suggestions and inherited politics memory are suspended until reviewed taxonomy provenance can distinguish domestic labels. Existing stored politics assignments remain visible for review. The exporter rejects unmigrated conflict assignments rather than silently omitting them.

## Review and compare

1. Verify record counts and exact split membership against the old bundle.
2. Review the pilot under the new definitions; preserve deliberate disagreements in notes.
3. Settle the separate tie/output-count policy before model evaluation.
4. Freeze the rubric and reviewed-label version. Record taxonomy, label, model, and prompt versions with results.
5. Compare all candidates using the same version. Historical v1 results remain v1 results; do not silently rename their interpretation.

The source converter supports source schemas 1 and 2 with taxonomy v1 or v2. It checks the declared version rather than guessing from tag names. A v1 row containing `international-politics`, or a v2 row containing `conflict`, is rejected.
