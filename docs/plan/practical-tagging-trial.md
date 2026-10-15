# Practical review trial: method

**Historical study, 6 October 2026.** The [recorded outcome](../results/practical-trial.md)
reports 20 cases reviewed by one person. This protocol is not a new request for
labeling or provider calls. Use the [original revision](../research-replay.md) for replay.

## Selection and workflow

The study selected 20 event types from the public feed’s 6 October–31 December
window. A frozen registry excluded previously seen titles. Normalized word-set
overlap of at least 0.55 or character similarity of at least 0.78 screened for
related wording. A fixed hash order selected 7 short, 7 medium and 6 long titles,
then rotated workflow assignments within each stratum.

The three workflows contained 7 manual, 7 Qwen and 6 Gemini cases. Each event
appeared once. Text/length matching does not guarantee equal difficulty or exclude
semantic overlap and personal familiarity. Related remembrance cases were later
found; the results preserve the original run and show sensitivity analyses.

## Fixed model requests

Qwen/Qwen3.6-35B-A3B-FP8 on Hetzner and gemini-3.8-flash received the original
title and rubric v3, search off, with at most two topic tags. Reviewer references
could retain every supported topic. Qwen used temperature zero and thinking off;
Gemini used provider defaults. The two request templates are in the
[v1 configuration](../../notebooks/prompts/practical-tagging-v1.json).
Its personal provenance is redacted in the public copy; original hashes identify
the original revision. The experimental three-tag policy did not replace v1.

## Measurement

The [review notebook](../../notebooks/18_practical_tagging_trial.ipynb) revealed
one event at a time, with Start/resume, Pause, Looking up context and Save controls.
Active time included reading, tag choice, notes and unpaused lookup. Original
model latency was recorded separately because suggestions were prepared in advance.
Private reviews preserved familiarity, context use, uncertainty and any sources.

Final answers entered after seeing a model suggestion are assisted decisions,
not an independent answer key. Precision/recall against them are descriptive
agreement only, and the models handled different events. Keep unrelated benchmark
quality evidence separate from this trial’s effort measurement.

## Interpretation

No reliable causal time-saving effect or overall winner was established. Small
batches, familiarity, semantic overlap and inconsistent lookup fields limit the
conclusion. Future trials should balance likely learning effects before observing
results and distinguish active reviewer effort from waiting and cache playback.
Transport failures, retries, usage and completed invalid answers remain recorded.
