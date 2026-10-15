# Research results

Results below describe distinct studies. Read the [methodology and limitations](../methodology.md)
before comparing numbers. One reviewer supplied the reviewed references.
Private records and model responses are not part of this public package.

## Main comparisons

| Study | Cohort and question | Result |
| --- | --- | --- |
| [Original final benchmark](../plan/final-evaluation.md) | 121 eligible final groups; regex, TF-IDF and Qwen under fixed rules | Qwen led; no candidate met all quality targets |
| [Reconciled development comparison](reviewed-comparison.md) | Saved predictions scored against a consistent reviewed reference | Shows reference sensitivity; not a new untouched final test |
| [Rubric v3/v4 comparison](rubric-v4-comparison.md) | Same 54 familiar reviewed cases in both conditions | Better agreement on familiar cases; policy and examples changed together |
| [Fresh v4 confirmation](fresh-v4-confirmation.md) | 34 fresh primary cases, plus broader/context subsets | Precision and coverage passed; recall stayed below 80% |
| [Practical review trial](practical-trial.md) | 20 cases across manual, Qwen and Gemini review | No reliable causal staff time saving established |

## Diagnostic and policy studies

- [Reviewed disagreements](error-analysis.md) and [accepted outcome](reviewed-outcome.md)
- [Two tags versus a third tied tag](tag-policy.md)
- [Confidence warnings](confidence-diagnostic.md)
- [Background knowledge and full-rubric context](background-knowledge.md)
- [Full versus current-rule delivery](reviewed-rubric-delivery.md)

## Supporting research reviews

- [Data/reference and LLM-engineering review](../audits/2026-10-06-tagging-quality-audit.md)
- [Rubric-v4 challenge](../audits/2026-10-06-rubric-v4-review.md)
- [Fresh-run scoring and interpretation checks](../audits/2026-10-07-fresh-v4-run-audit.md)

These dated reviews retain useful evidence and methodological caveats. They are
AI-assisted technical checks, not independent reference-label review or certification.
Historical filenames are retained so existing references remain traceable.
Operational publication logs are maintained separately in the issue tracker.

See [research replay](../research-replay.md) for the original source revision and
required private evidence. New calls are not a replay of old cached predictions.
