# Practical review outcome

All 20 reviews are complete. Nineteen answers are resolved and one remains unclear. Saved review hashes, event IDs, title fingerprints and prediction links have been verified.

## What happened

| Workflow | Cases | Median active time | Suggestions accepted unchanged |
|---|---:|---:|---:|
| Manual | 7 | 61.4 seconds | Not applicable |
| Qwen3.6 on Hetzner | 7 | 107.1 seconds | 3/7 |
| Gemini 3.8 Flash | 6 | 69.2 seconds | 2/6 |

Qwen suggestions required changes on 4 of 7 events (three tags added, four removed). Gemini required changes on 4 of 6 (five tags added, one removed). Both models returned suggestions for every assigned case, with no provider failures. The median original request times were 1.28 seconds for Qwen and 7.14 seconds for Gemini; suggestions were prepared before review. Human time includes reading, choosing tags, entering answers and notes, and any unpaused context lookup.

## Repeated topic and sensitivity check

Three differently worded cases concern remembrance of the 1938 pogroms, one in each workflow. The text-similarity screen missed their shared subject. A later review explicitly refers to the preceding example. This can create a learning effect; it does not establish identical events or organizers. Preserve the original run and show an additional exclusion check instead of deleting rows after seeing scores.

| Analysis | Manual: n / median seconds | Qwen: n / median seconds | Gemini: n / median seconds |
|---|---:|---:|---:|
| All reviews | 7 / 61.4 | 7 / 107.1 | 6 / 69.2 |
| Exclude three remembrance cases | 6 / 76.2 | 6 / 144.7 | 5 / 67.6 |
| Unfamiliar only, exclude remembrance cases | 5 / 91.0 | 5 / 107.1 | 5 / 67.6 |

The ranking changes when related or familiar cases are removed. Gemini is faster in the exclusion checks, but these are small, different batches and post-hoc analyses. No reliable causal time saving or winner is established. A future timing study needs semantic topic/series screening as well as textual matching; record and balance likely learning effects before the run.

## Quality and context limits

Assisted agreement with the reviewer’s final answers was Qwen: 63.6% precision / 70.0% recall; Gemini: 88.9% / 61.5%. These answers were entered after suggestions were visible. They are not independent quality measurements, and the two models handled different events. Keep the prior benchmark as the quality evidence.

Eight reviews say context was needed. Five of those record zero lookup time; three other reviews record lookup time despite saying context was not needed. These combinations may reflect how the controls were interpreted. Clarification is pending; do not infer verified research duration from these fields.

## Next decision

The delivered service retains review; this trial does not demonstrate a faster workflow. The current evidence does not justify claiming a faster or target-quality workflow. More model variants are not the immediate priority. No further labeling is requested for the completed DR-58 trial.

Costs: confirmed-free Hetzner $0; Gemini conservative usage upper estimate $0.057381. No new provider calls were made for this audit. Private sources: `reports/practical-trial/v1/human-results-v1.json` and `audit-v1.json`.
