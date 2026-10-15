# Final evaluation: results and recommendation

**Completed 1 October 2026.** [Notebook 10](../../notebooks/10_final_benchmark_and_recommendation.ipynb) evaluates all three accepted candidates on **121 eligible final event groups**. Qwen gives the strongest result, but no candidate meets the combined targets of 80% precision, 80% recall and 95% coverage. Keep reviewer approval.

## Results

| Candidate — strict two suggested tags | Precision | Recall | F1 | Coverage | Exact tag-set match |
|---|---:|---:|---:|---:|---:|
| Production regex | 50.0% | 25.4% | 33.7% | 64.5% | 12.4% |
| Word + character TF-IDF logistic regression | 60.2% | 29.6% | 39.7% | 60.3% | 14.9% |
| Qwen/Qwen3.6-35B-A3B-FP8 on Hetzner, title only | 73.2% | 59.3% | 65.5% | 100.0% | 38.0% |

These are final-test results on the same 121 groups, not the earlier twelve-case review or targeted development sample. Qwen makes 153 suggestions: 112 match the reference and 41 do not. It misses 77 of 189 reference tags. Full coverage means every event receives a suggestion, not that every suggestion is correct.

Regex leaves 43 events without suggestions; TF-IDF leaves 48. In the separately reported exact-tie policy, regex F1 is 35.6% and TF-IDF remains 39.7%. No settings were changed after inspecting final scores.

## Preserved configuration

| Candidate | Fixed settings |
|---|---|
| Production regex | Saved production-derived patterns and normalization; no new politics rule |
| Word + character TF-IDF | Saved one-versus-rest logistic regression and vocabularies; cutoff 0.30; no refit |
| Qwen/Qwen3.6-35B-A3B-FP8 | Exact corrected title-only rubric-v3 prompt checked in DR-47; temperature 0; at most two tags; no search |

The configurations were pinned before inspecting final references. Notebook 10 reproduces the saved regex and TF-IDF development predictions before running final inference. Final answers were not used for training, cutoff selection or prompt editing. DR-23 accepted this shortlist; Jev remains paused and the other experiments remain development evidence.

## Reference approval and duplicate exclusions

The original holdout has 123 selected event groups from 149 reviewed dated occurrences. Before inference, the reviewer approved five additions under rubric-v3: human-rights on four explicit Pride/anti-queer-hostility events, and politics on a German healthcare-law event. Existing labels were retained, including one three-tag reference. Reference tags are not truncated to fit model outputs.

Two final events were confirmed as duplicates of development records using matching dates, times and locations, with minor title differences. The reviewer approved excluding both before predictions. The primary score therefore uses 121 groups. This is a documented duplicate correction, not removal of difficult cases based on model performance. The original CSV and 123-group selection remain unchanged. Unknown overlaps may still exist.

Private evidence under `reports/final-benchmark/v1/` preserves the candidate contract, proposed and approved references, approval, manifest, local predictions, hosted responses, attempt logs and `results.json`. Files contain input fingerprints and fixed IDs. Keep them out of Git.

## Reliability, time and cost

All 121 Qwen requests succeeded on the first attempt; the returned model identity matched the requested model throughout. Its median original request time was 1.14 seconds, P95 1.84 seconds and maximum 4.92 seconds. This run met the under-five-minute waiting-time target. Local inference medians were about 0.0002 seconds for regex and 0.0013 seconds for TF-IDF, excluding artifact loading and training.

Qwen used 238,930 input tokens and 2,496 output tokens. Calls used the authorized free-tier account. Invoice charges and local compute costs were not verified, so the $1-per-event cost target is not marked as verified. Cached replay time is not inference time. The $50 experiment budget remains unchanged; no paid fallback was enabled.

Notebook 10 reuses saved answers and stops on transient provider outages. Terminal invalid responses would count as empty predictions; unattempted events would keep the batch incomplete. Neither occurred in this completed run.

## How certain are these results?

The notebook resamples event groups 2,000 times with a fixed seed. Its 95% bootstrap F1 intervals are 27.2–40.6% for regex, 32.7–46.7% for TF-IDF and 59.4–71.6% for Qwen. These intervals describe sample variability, not mistakes in the reference. Qwen's observed 100% coverage does not guarantee future coverage, even though its bootstrap interval collapses to 100%.

The reference review was focused, not a full independent second labeling pass. Some answers retain uncertainty or depend on background absent from the title. The trained classifier still uses historical training labels. Rare categories have limited evidence; education has two reference examples. Do not claim general production performance or causally attribute the difference from development scores to one factor.

## Recommendation and review steps

Keep reviewer approval. Qwen is the strongest candidate here for a reviewed suggestion workflow, but it does not meet the agreed quality gate. A prototype can be considered only with an explicit revised objective and acceptance criteria; this benchmark does not justify automatic application. Any later tuning requires new independent evaluation data for a new final claim.

1. Use [the original research revision](../research-replay.md), then open Notebook 10 with the matching private artifacts available.
2. At that original revision, keep `NOTEBOOK10_RUN_LIVE=false` and Run All. This replays saved answers without API calls.
3. Confirm 123 original groups, two excluded duplicates and 121 primary groups.
4. Review the result table, graph, per-tag support and recommendation. No new CSV review is required.
5. Keep the original comparison separate from later development and fresh-case follow-ups.

Notebook 09 remains the development-selection record. DR-47's search-result experiment used ten development cases and did not improve Qwen; it is not part of this final title-only comparison.
