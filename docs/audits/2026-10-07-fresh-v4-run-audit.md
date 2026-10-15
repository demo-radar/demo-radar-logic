# DR-69 audit — correct calculations, uncertain error attribution

Historical research review. Read the [current methodology](../methodology.md) and [results index](../results/README.md) for the delivered conclusion. This is an AI-assisted technical review, not independent reference-label review or certification.

**7 October 2026 · Notebook 23 · Gemini 3.8 Flash and Qwen3.6**

## Conclusion

**The saved run and reported scores are reproducible. No request-mapping, parsing or scoring error was found. However, a missing reference tag is not automatically a model mistake.** Some references use broader interpretations than the written rubric, some require information the models did not receive, and some exceed the two-tag output limit.

The earlier conclusion, “the remaining problem is incomplete topic coverage,” was too definite about the cause. It should say **incomplete agreement with the reviewer reference**. This correction matters: improving a model and making the answer key consistent are different tasks.

This audit was performed by Codex, with a separate offline decoder and scikit-learn calculation. It is not an independent human labeling review. No provider requests were made, and no labels, prompts, selection rules or original results were changed.

## 1. Technical checks

| Check | Finding |
|---|---|
| Selection and grouping | Saved selection reproduced; 40 unique case identities. This verifies the recorded method, not the absence of every possible semantic relationship. |
| Model inputs | All 80 requests match the pinned model settings, original title and full v4 rubric. No reference answers, translations or private notes were sent. |
| Search | Off in every payload and saved Gemini tool record. Learned knowledge remained allowed. |
| Completion and retries | 40 successful requests per model; one recorded attempt each. No truncation, missing response or hidden retry was found. |
| Cache and reports | All 80 cached records match the final report. Returned model names match the requested aliases; aliases do not pin immutable weights. |
| Output parsing | Tags independently decoded and matched. Gemini wrapped 23 answers in Markdown fences; the existing parser correctly removed those fences. “Valid” means valid after this normalization, not perfect adherence to bare-JSON formatting. |
| Scoring | All four cohorts, every per-tag count, precision, recall, F1, coverage and exact match reproduced. The two unclear cases have no correctness score. |
| Cost and timing | Original durations reproduced; the conservative paid total matches the shared ledger. No new charges arose from this audit. |

The main subset still contains **34 cases and 64 reference tags**:

| Model | Matching tags | Extra tags | Missing reference tags | Precision | Recall | F1 | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen/Qwen3.6-35B-A3B-FP8 | 47 | 7 | 17 | 87.0% | 73.4% | 79.7% | 97.1% |
| Gemini 3.8 Flash | 49 | 7 | 15 | 87.5% | 76.6% | 81.7% | 97.1% |

There is one saved generation per model/case. Gemini used provider-default sampling and thinking; Qwen used temperature 0 with thinking disabled. These are the approved configurations, not a matched reasoning-budget experiment. The audit cannot estimate repeat-run variation.

Gemini's F1 lead is **2.0 percentage points**. An exploratory paired case bootstrap gives a wide 95% interval of **−6.6 to +10.2 points** for that difference. This does not establish a reliable winner. The calculation resamples the same cases for both models, 10,000 times with seed 69; it cannot correct this filtered sample's selection limits or remaining topic dependence.

## 2. Could the reviewer reference be part of the problem?

**Yes. There is evidence of interpretation differences, but this run cannot establish personal or ideological bias.** One reviewer supplied the reference and helped define the rubric. A second independent human answer set is unavailable. Agreement between two models is also not proof that their answer is right.

The audit found three recurring questions:

| Boundary | Why the reference deserves scrutiny |
|---|---|
| Historical remembrance → human rights | Some references add human-rights to historical remembrance. The models sometimes return culture alone. The rubric does not clearly settle when historical rights violations require both tags without a present rights demand. |
| Event format → culture | A run or a literary quotation influenced culture choices. The rubric also says to distinguish format from purpose. Its inclusion of sport leaves room for different readings of a charity run. |
| Social care → social-issues | Both models recognize a care/support topic in a case labeled inclusion plus culture. Human-rights and social-issues are not mutually exclusive; a supported care purpose can justify both. |

Across the fresh subset, both models omit the **same four human-rights assignments and three culture assignments**, spread over **six cases**. These are the priority cases for understanding the disagreement. Some combine multiple limitations; seven shared omissions are not seven confirmed labeling errors.

One of these cases has three accepted tags based on an earlier-year event and a general organizer page. Both models abstain. Approval preserved that interpretation; it did not verify the current event's three topics. Another has four reference tags: neither model was permitted to return all four.

The broader 38-case comparison also contains two deliberate politics exceptions that the models were not given. Both models follow the written v4 rule there. Those disagreements must remain visible as policy mismatches. They do **not** explain the main 34-case score, which excludes both cases.

## 3. Model mistakes also remain

The reference concerns do not explain everything. Qwen assigns domestic politics to an explicitly foreign political subject and misses the international component of a demand about a foreign law. Gemini misses politics in a title explicitly centered on drug policy. These are stronger examples of model error under the current rubric than an ambiguous remembrance overlap.

The strict two-tag cap makes at least **five omissions unavoidable**. Perfect capped output could recover 59/64 tags, or 92.2% recall. Actual omissions are 15 and 17. Do not attribute all misses to the cap, and do not remove reference tags just to improve recall.

Agreement cases were checked too. Some review explanations need care even where both models match: a healthcare-sector reference needs a work-related subject, not just an association with workers; another note says health is absent although the title mentions it. These are evidence/explanation concerns, not automatic instructions to change tags.

## 4. Spending: three different figures

| Figure | Meaning |
|---|---|
| **€4.72 spent; €4.02 remaining** | Latest user-reported dashboard figures. Its reporting period and allocation to this run were not independently verified. |
| **$0.298692** | This run's usage-based estimate: input at $0.75/million; output including thinking at $3.75/million. Before invoice adjustments, tax or currency conversion. |
| **$0.842444** | Existing budget guard total. It deliberately treats all reported tokens as output-priced tokens and rounds each request upward. It is a conservative allowance, not measured billing. |

Recorded Gemini usage: 181,246 input tokens, 697 visible output tokens and 42,705 thinking tokens; no cached or tool-use tokens. The two rates are the run's pinned [official Gemini prices](https://ai.google.dev/gemini-api/docs/pricing). Qwen used the confirmed free Hetzner account.

The guard is about **2.8 times** the usage-based estimate here. Explaining that difference is more useful than presenting the guard as expected spending. The ledger remains conservative; it was not rewritten from an unallocated dashboard balance. Do not add the dollar estimate to the euro total or infer the run's invoice from the balance alone.

## 5. Recommended next step

1. **Keep these results as the v4 record.** No score is replaced by a more favorable subset or revised answer key.
2. **Use the six shared-omission cases to settle two reusable boundaries:** historical remembrance versus human-rights, and event format versus culture/social care. Separately distinguish verified event context from organizer background. No full relabeling exercise is needed to understand these issues.
3. **If the policy changes, create a separate version.** Review affected examples, including model-agreement cases. Rescore both models consistently; identify that as a post-run correction, not fresh confirmation. Do not call a v5 prompt better until it is tested against v4 under the same approved reference.
4. **Take the audited evidence to DR-27.** It supports considering suggestions with mandatory reviewer approval. Automatic tagging, a reliable model winner and human time savings remain unproven. More paid calls on the same cases are not the next priority.

The private case appendix contains the titles, current tags, saved predictions, relevant rules and source limitations. These are audit observations, not a new answer key or a request to redo all 40 reviews.

## Reviewer follow-up — 7 October

The reviewer subsequently accepted several model outputs as reasonable, including abstention on a vague title, a social-care reading instead of culture, and an international-only political reading. Other omissions remain unacceptable to the reviewer, especially human-rights in historical persecution/remembrance. A religion suggestion was explicitly rejected for one event. These responses support mixed causes, rather than treating all reference mismatches as model errors or reviewer bias.

Both candidates received the same title and complete rubric, with search off and learned knowledge allowed. Better use of particular words on some cases does not prove a model had additional context; tags-only outputs do not reveal the reason for its choice. A tag associated with a mentioned location or public-space phrase can reflect over-weighting that detail rather than fabrication of facts.

The private case notes record the feedback, including a corrected case-number reference. No reference answers, rubric rules or scores changed. Candidate clarifications concern historical remembrance and human-rights, religious context versus religious purpose, and central demands versus incidental setting or event format. These require a separate policy/reference version before any new comparison.

## Evidence and reproduction

- [Original aggregate result](../results/fresh-v4-confirmation.md) and [Notebook 23](../../notebooks/23_fresh_v4_confirmation.ipynb).
- Private inputs: `reports/fresh-confirmation/2026-10-07/`.
- Private audit: `comparison-v1/audit-review/checks.json`, `case-notes.md` and `reproduce.py` under that folder. The check records hashes of original inputs and verifies they stayed unchanged.
- From the repository root, run `uv run --locked --group notebooks python reports/fresh-confirmation/2026-10-07/comparison-v1/audit-review/reproduce.py`. It reads saved responses and writes only audit checks; it cannot call a provider.

DR-69 is now Done on Jira, closed by the user. The bounded follow-up is [DR-70’s three-rule proposal](../rubrics/v5-boundary-review.md). The audit and draft change interpretation/documentation, not the original scoring contract.
