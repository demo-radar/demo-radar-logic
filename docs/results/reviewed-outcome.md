# Reviewed outcome

Four accepted answers changed. Two additional events are unclear, leaving 54 accepted events and three unresolved events in the 57-event union. No predictions or rubric definitions changed.

The table holds the 54 event IDs fixed. Before uses DR-55 answers; after uses DR-61 answers. Coverage cannot change when only reference tags change.

| Candidate | Before F1 | After precision | After recall | After F1 | Coverage |
|---|---:|---:|---:|---:|---:|
| Qwen/Qwen3.6-35B-A3B-FP8 — simple rubric | 74.4% | 77.1% | 72.7% | 74.9% | 100.0% |
| gemini-3.5-flash-lite — simple rubric | 72.6% | 75.9% | 68.2% | 71.9% | 98.1% |
| gemini-3.8-flash — simple rubric | 73.0% | 82.9% | 65.9% | 73.4% | 92.6% |
| gemini-3.8-flash — Gem search_off | 74.7% | 87.0% | 68.2% | 76.4% | 92.6% |
| gemini-3.8-flash — Gem search_on | 73.5% | 89.4% | 67.0% | 76.6% | 90.7% |
| Qwen/Qwen3.6-35B-A3B-FP8 — Gem search_off | 74.1% | 80.8% | 67.0% | 73.3% | 100.0% |
| Production regex | 50.6% | 60.0% | 44.3% | 51.0% | 77.8% |
| Word TF-IDF + logistic regression | 48.1% | 55.4% | 40.9% | 47.1% | 79.6% |
| Word + character TF-IDF + logistic regression | 52.1% | 69.8% | 42.0% | 52.5% | 70.4% |
| TF-IDF F3 context | 47.3% | 44.3% | 48.9% | 46.5% | 98.1% |
| Multilingual NLI | 32.5% | 36.6% | 29.5% | 32.7% | 88.9% |
| German GBERT NLI | 31.6% | 29.7% | 34.1% | 31.7% | 98.1% |

## What the review teaches us

- Reference corrections can add a missing topic or remove an unsupported topic. They need not benefit both models equally.
- One agreement control became unclear. Agreement between the models and the old answer is not proof of correctness.
- Location and background reports help identify context but do not automatically establish the demands of a specific event. One healthcare reference retains a labor interpretation with a date-matching limitation.
- Labels describe subjects, not whether an event supports or opposes them. Opposition to development can still concern housing.
- No general rubric meaning change was approved. Preserve case-specific interpretations and source gaps rather than treating them as new rules.
- The sample is small, targeted and repeatedly reviewed by one person. These results cannot establish production accuracy or erase the models’ own mistakes.

## Next step

Review section 8 of Notebook 16. No more labeling is requested for DR-61. Keep the practical shortlist unchanged and test the third-tag policy under DR-60, separately from reference corrections. DR-24 cost reconciliation is still required before the service decision.

Private source: reports/error-analysis/2026-10-05/approved-reference-v1.json. Private paired metrics: reports/reconciled-comparison/dr61-v1/results.json.
