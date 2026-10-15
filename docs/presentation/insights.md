# Research lessons

These lessons connect the experiments to the delivered service. Detailed
aggregate results remain in the [results index](../results/README.md); internal
weekly schedules, approval conversations and local recovery logs are in the
project’s issue tracker. Historical replay uses the [recorded revision](../research-replay.md).

## The answer key changes the measured result

Rescoring unchanged predictions against revised references changes a score without
changing the model. Targeted disagreement reviews cannot estimate a production-wide
label-error rate. References need versioning, explicit policy and uncertainty.
Model agreement is not independent proof that the reference is wrong.
See the [reconciled comparison](../results/reviewed-comparison.md).

## Coverage is not correctness

A system can suggest something for every event and still miss many supported
topics. The [original final comparison](../plan/final-evaluation.md) reports
precision, recall, F1, coverage and complete tag-set match together. More input
features and lower cutoffs can increase suggestions without improving agreement.

## A high NLI score can hide a neutral answer

The invented Protect Pigs diagnostic exposed a binary score computed as support
divided by support plus contradiction, excluding neutral. Tiny support can yield
a high ratio when contradiction is even smaller. Inspect all three NLI outputs,
not just the derived score. This is a scoring lesson, not proof of political bias
or failure of every semantic model. See [Notebook 06](../../notebooks/06_semantic_models.ipynb).

## Search must execute and earn its cost

A search-enabled setting does not establish that retrieval happened. Studies
recorded tool traces and citations separately from tagging answers. Verified
retrieval still did not consistently improve these comparisons, and extra text
can add irrelevant or mismatched-event context. This does not rule out targeted
research where information is missing. See [Notebooks 08, 12, 13 and 15](../../notebooks/README.md).

## Clearer policy needs a fresh check

On 54 familiar cases, the complete v4 package improved F1 by 6.4 percentage points
for Qwen and 9.3 for Gemini. Those cases helped shape the rubric, so the result
needed a separate check. On 34 fresh cases, both candidates met precision and
coverage targets, but neither reached 80% recall. These cohorts do not form one
improvement curve. See the [paired rubric study](../results/rubric-v4-comparison.md)
and [fresh confirmation](../results/fresh-v4-confirmation.md).

## A correct calculation can still have an uncertain reference

The fresh-run review reproduced scores but found reference/context and output-cap
limitations. Some complete references exceed two tags. Some demands were inferred
from sources the model did not receive. Preserve these constraints rather than
calling every omission a proven reasoning error. The [technical review](../audits/2026-10-07-fresh-v4-run-audit.md)
is an AI-assisted consistency check, not another human labeling exercise.

## Faster inference does not prove less staff work

The 20-case [practical trial](../results/practical-trial.md) measured active
review separately from prepared model answers. Small different batches, familiarity,
related topics and lookup-recording issues prevented a reliable causal claim.
Track corrections, backlog and staff minutes as product outcomes; model latency
alone cannot establish useful automation.

## A timeout is an unknown outcome

A lost reply can still correspond to a completed or billed model request. Stable
request IDs, durable saved answers and one admission gate let the application
recover without blind resends. Uncertain work pauses tagging and summaries; an
audited recovery decision retains history and missing usage. A restart or elapsed
wait does not prove remote work stopped. See [service recovery](../service-api.md#what-happens-if-the-connection-drops).

## The delivered boundary matters

DemoLogic prepares an answer. Demo Radar owns records, staff permissions and the
decision to publish. Separate frontend, backend and AI responsibilities make
review, testing and future provider changes easier to reason about. The
[architecture decision](../adr/0001-capstone-backoffice-ml-vs-llm.md) records this
boundary without treating the research recommendation as automatic approval.
