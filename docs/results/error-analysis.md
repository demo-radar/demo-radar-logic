# Model disagreement or answer-key gap?

5 October 2026. Follow-up to DR-26; no new model calls or label changes.

## What the saved outputs show

The same 56 reviewed events contain 92 reference tags. Qwen3.6-35B-A3B-FP8 (simple rubric) suggests 85 tags: 66 match the reference, 19 are extra and 26 reference tags are missed. Gemini 3.8 Flash (simple rubric) suggests 72: 60 match, 12 are extra and 32 are missed. These are comparisons with accepted answers, not proof of model or human error.

The outputs differ on 33 events and agree on 23. Of the agreements, 17 match the reference exactly and 6 do not. Both omit the reference politics tag on 10 events.

| Tag | Reference support | Qwen missed | Qwen extra | Gemini missed | Gemini extra |
|---|---:|---:|---:|---:|---:|
| culture | 9 | 6 | 1 | 2 | 4 |
| education | 0 | 0 | 1 | 0 | 0 |
| environment | 4 | 0 | 0 | 1 | 0 |
| housing | 5 | 0 | 1 | 1 | 0 |
| human-rights | 18 | 3 | 11 | 7 | 2 |
| international-politics | 11 | 1 | 1 | 3 | 1 |
| lgbtq | 4 | 1 | 1 | 3 | 1 |
| mobility | 3 | 0 | 1 | 0 | 0 |
| politics | 23 | 12 | 0 | 11 | 1 |
| religion | 0 | 0 | 0 | 0 | 2 |
| social-issues | 9 | 2 | 2 | 3 | 1 |
| work | 6 | 1 | 0 | 1 | 0 |

## Interpretation before further changes

- Qwen produces more suggestions, gaining recall but adding more tags absent from the reference. Most of its extra suggestions are human-rights.
- Both frequently miss reference politics assignments. Some references depend on context or an interpretation broader than the written rule; agreement between models does not resolve that conflict.
- Education and religion have no positive references in this sample. Recall for these categories cannot be assessed; zero omissions do not mean perfect performance.
- Four references contain three tags. Even a perfect two-tag model could reach only 88/92 = 95.7% recall, but that limit explains only a small part of the observed missing tags.
- Previously reviewed cases are not independent, blind answers. Repeated corrections cannot establish population accuracy.

## Bounded review

The private packet `reports/error-analysis/2026-10-05/review.md` contains eight purposive judgment questions and two agreement controls. It hides saved labels and model outputs; it does not claim reviewer blinding or representative sampling. Recent DR-55 decisions are carried forward. Selection and all 56 event-level comparisons are preserved privately in `analysis-v1.json`.

Review missing reference tags, unsupported reference tags, model interpretation errors, rubric ambiguity, missing context and output-limit effects separately. Do not auto-correct labels from model consensus. A general rule change needs a new rubric version and an impact review beyond this packet; do not silently apply it to the final benchmark.

## Next step

After the answers are accepted, version any corrections and compare all saved candidates consistently. Keep DR-26 Done. Complete this diagnostic before DR-60; continue DR-24 accounting alongside it. No new provider calls or model variants are required.

## Review completed

The ten decisions and chat clarifications are now recorded. See the [reviewed outcome](reviewed-outcome.md) for the paired comparison on 54 retained events. Earlier analysis above remains the pre-review record. No further labeling is requested.
