# Rubric review decisions recorded

**6 October 2026.** Read [rubric v4](tagging-rubric-v4.md) for the policy supplied in full in DR-67. The six decisions are recorded. D1–D5 retain the previous reference tags; D6 adds `human-rights`. No other label changed.

**Update after DR-67: v4 improved both models on the 54 reviewed development cases.** Gemini F1 rose by 9.3 points to 85.1%; Qwen rose by 6.4 points to 82.0%. Both meet 80/80/95 on this familiar sample, with per-tag tradeoffs. Read the [paired results](../results/rubric-v4-comparison.md). The older table below is a separate offline answer-key check and does not show the v4 experiment.

## What changed in the policy

| Area | Recorded direction |
|---|---|
| Model knowledge | Models may use learned knowledge, the rubric and supplied context. Search off disables live retrieval, not knowledge. |
| Environment | Include carbon emissions and protests about the physical expansion of data centers or large companies. |
| Mobility | Include street use, speed limits and traffic safety. “Emotions topics” provisionally means traffic-related fear/stress; clarification was requested. |
| Housing | Public-space protection can overlap with environment. Opposition to building still concerns development. |
| Work | Include staffing limits, workplace training limits, overtime and employment-related tax burdens. Add politics when the demand is to change German tax policy. |
| Education | Require an educational subject; a university/campus location is insufficient. |
| LGBTQ | Civic colorful/diverse language can signal LGBTQ inclusion. Literal colors, biodiversity and animal-rights diversity do not imply LGBTQ. This is an interpretive project policy, not a universal equivalence. |
| Domestic politics | Include recognizable calls for political action and democracy in Germany, without requiring a named law or politician. |
| International politics | Include foreign affairs, support/opposition to countries, public peace appeals and political controversy involving foreign-linked institutions. |
| Human rights | Explicitly include humanitarian aid, demining and civilian protection. |
| Culture | Include actual singing, dancing and storytelling programs. A current-event vigil, including one about an ongoing war, is not automatically culture. An actual cultural program can still qualify. |
| Religion | Include religious figures, sites as subjects, teachings and food practices such as kosher. |

These are changes in meaning and examples, not merely a shorter document. V4 incorporates the user's interpretation policy. The rules should be judged for consistency and usefulness, not treated as established universal category boundaries.

## Reference decisions

- **D1–D5:** retain the accepted tags, including the reviewer interpretations and source limitations. The hypothetical extra international tag mentioned in D1 was not applied because the final instruction explicitly changed only D6.
- **D6:** add human-rights for the explicit civil-liberty demands.
- **Same cohort:** 54 accepted cases, now 89 reference-tag assignments; three previously unresolved records remain excluded. No difficult case was removed.
- The pasted Instagram account of D5 is retained privately. Its URL, date and event match were not independently verified in this turn. It supports the reviewer's explanation, not a new verification claim.
- The reviewer's statement that the answers are 95% accurate is a personal assessment, not a measured accuracy result.

The original CSVs and DR-61 answer key remain unchanged. The revised private reference is `reports/rubric-revision/v4/approved-reference-v1.json`; `decisions-v1.json` preserves the review reasons and provenance.

## Offline check: changing the answer key only

Saved predictions from 20 configurations in the comparison registry were rescored. Eighteen cover all 54 cases; all twenty share a separately reported 31-case subset. That offline check made no model calls and did not supply v4. Coverage stays unchanged because predictions are fixed.

For the latest full-v3-document controls from DR-65:

| Model | Reference | Precision | Recall | F1 | Coverage |
|---|---|---:|---:|---:|---:|
| gemini-3.8-flash | Previous 88 tags | 84.0% | 71.6% | 77.3% | 98.1% |
| gemini-3.8-flash | Revised 89 tags | 84.0% | 70.8% | 76.8% | 98.1% |
| Qwen/Qwen3.6-35B-A3B-FP8 | Previous 88 tags | 71.0% | 75.0% | 72.9% | 100.0% |
| Qwen/Qwen3.6-35B-A3B-FP8 | Revised 89 tags | 72.0% | 75.3% | 73.6% | 100.0% |

These small changes come entirely from the newly accepted tag. They are not a result of the revised prompt. The complete per-configuration and per-tag metrics are private in `reference-only-rescore-v1.json`. Reproduce with `uv run --locked python reports/rubric-revision/v4/rescore.py`.

## Comparison protocol — subsequently completed in DR-67

1. Finalize the exact request payloads using complete v3 and v4 documents and the revised references. Both conditions permit learned knowledge; search remains off. No real reviewed examples, answers or notes enter the prompts. Keep the existing strict two-tag model setting and retain every reference tag.
2. Compare Gemini 3.8 Flash and Qwen/Qwen3.6-35B-A3B-FP8 on the same 54 reviewed titles with fresh paired controls and alternating condition order: at most 216 scheduled requests. Hold other model settings fixed.
3. Price and reserve the batch in the existing budget ledger. The DR-66 comparison plans record scope but do not execute requests. DR-66 itself made no calls; DR-67 subsequently ran the comparison with a conservative paid usage estimate of $2.096456.
4. Report each prediction arm against the same revised reference; also retain the original-reference view. Show precision, recall, F1, coverage, per-tag changes, failures, speed and cost.
5. Keep the development screening rule: +3 percentage points F1, no more than 2 points lost in precision or coverage, then inspect regressions. Keep the project targets of 80% precision, 80% recall and 95% coverage.

The 54 cases shaped this policy and have been repeatedly examined by one reviewer. Any gain is development evidence, not an independent confirmation of performance on new events. V4 may suggest further overlaps on other accepted cases; those are disagreements to explain, not permission to silently rewrite their answers.

## Version handling

The original research revision preserves the exact v3 bytes and hashes. The public copy of `docs/tagging-rubric.md` now redacts personal provenance; use the [historical replay guide](../research-replay.md) instead of treating the redacted copy as identical. New experiments must explicitly load `docs/rubrics/tagging-rubric-v4.md`. This prevents an old notebook from silently running with new rules. The old draft link redirects to the completed v4 document; prior draft content remains in the private research archive.

The paired comparison is complete; the original decisions and results remain recorded. Mobility's “emotions” wording remains provisional. The independent challenge below records the approved tax-policy rule.

## Independent challenge — 6 October

A separate AI reviewer challenged the rubric before closure. [Read the technical findings](../audits/2026-10-06-rubric-v4-review.md). The ongoing-war clarification, tags-only response instructions and history/education boundary are incorporated. After the review, the user approved work + politics when the demand is to change German tax policy. The rule and invented tax example now match; a contrasting work-only example covers discussion without a policy-change demand. Mobility's earlier “emotions” phrase remains provisional. The independent reviewer considers a bounded comparison possible with these choices recorded. The recorded reference labels and offline scores above have not changed.

Notebook 22 uses the correct rubric version in each request wrapper and identical response-schema instructions in both arms. Report the five three-tag cases and the 94.4% maximum recall under the two-tag cap. Treat reference disagreement, unsupported inference and model error as different possible explanations.

The earlier approved-reference file still fingerprints the policy as it existed when the six decisions were recorded. That exact Markdown is preserved privately by hash under `reports/rubric-revision/v4/rubric-history/`. The new comparison-plan-v2 records the revised candidate document separately; the old reference, rescore and plan files are preserved.
