# Replaying historical research

The public source package contains the current service, synthetic checks and
redacted research documentation. **Earlier research commits are kept in a
separate private archive. They are not part of the public snapshot.**

## Authorized historical replay

Obtain the private Git bundle and matching research inputs through an authorized
handoff. The bundle preserves source history; it does not contain the ignored
private datasets, saved responses, fitted artifacts or runtime settings.
The public repository alone cannot reproduce the withheld benchmark scores.

Use a separate directory so existing private inputs and working changes are not
overwritten. Replace the example path with the private bundle's actual location:

```bash
RESEARCH_BUNDLE="/path/to/private/research-history.bundle"
git clone "$RESEARCH_BUNDLE" demologic-research-replay
cd demologic-research-replay
git checkout a43be26bde2f7283baefca1580d712b487860b19
uv sync --locked --group notebooks --group service
```

That revision preserves the research inputs before public redaction. Obtain each
study's matching private evidence separately. Keep the archive, its replay
checkout and private inputs out of public repositories and release packages.
Do not copy credentials into a shared checkout.

## What changed and what did not

Personal review provenance was redacted from the public v3 rubric and the older
practical-trial configuration. Some notebook explanatory text and chart labels
were also cleaned. Their original fingerprints intentionally remain the record
of the original experiment. Do not update a saved run’s hashes or disable its
checks to make redacted inputs appear identical.

The deployed v4 rubric, inference/summary catalogs and service configuration were
left byte-for-byte unchanged by the documentation cleanup. Research scores,
case membership and private saved answers were not recomputed or modified.

## Replay requirements

Use the original revision, the matching snapshot/benchmark/review bundle, saved
predictions or cache, fitted artifacts where required, and that study’s pinned
configuration. Early notebooks also predate later rubric revisions; follow their
recorded source hashes and original study revision rather than substituting the
latest rubric. Missing or mismatched input is a reason to stop, not weaken validation.

Keep live modes off when reviewing saved experiments. New calls require separate
provider credentials, current price/limit checks and explicit approval; they may
not reproduce old outputs because hosted aliases and defaults can change.
For natural-language inference, model downloads and the locked semantic dependency
group are additional requirements. See the [notebook index](../notebooks/README.md).

Without the private evidence, readers can inspect code and aggregate results and
run the [synthetic workflow](reproducibility.md). They cannot independently
reconstruct the withheld benchmark scores. AI-assisted consistency checks do not
provide an independent reviewer reference review.
