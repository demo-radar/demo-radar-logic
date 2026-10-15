# Independent challenge of rubric v4

Historical research review. Read the [current methodology](../methodology.md) and [results index](../results/README.md) for the delivered conclusion. This is an AI-assisted technical review, not independent reference-label review or certification.

**6 October 2026 · DR-66 · another AI reviewer, not a second reviewer**

**Verdict:** v4 can support a bounded development experiment with the current policy choices explicitly recorded. The tax-policy conflict was resolved by the user after the review: a demand to change German tax policy receives work + politics when work is also central. The review found useful corrections, but **it did not establish any improvement in model performance**. Neither Gemini nor Qwen has been run with v4.

A separate reviewer read the rubric and change record, checked the preserved response contract, and inspected the reference counts. The primary agent checked the findings before editing. Broad definitions explicitly chosen by the user were treated as project policy, not silently reversed.

## Findings and action

| Priority | Finding | Why it matters | Action |
|---|---|---|---|
| High | The rubric asked models to report uncertainty/status, but the response permits only `tags`. | A model following the prose could return an invalid answer. | Fixed: review statuses are for human records. Tags-only calls return supported slugs or `[]`. An empty list does not distinguish uncertainty from no matching tag. |
| Medium | Historical learning could receive both education and culture, while examples said culture only. | A careful model could reasonably disagree with the example. | Fixed: historical storytelling/interpretation alone is culture; education needs a distinct educational-system, provision, access, teaching/research or training subject. |
| Medium | A tax-reduction example says work only, while the politics rule includes calls for German political action. | The policy allows two plausible answers. | Resolved by the user after review: work + politics when the demand is to change German tax policy and work is central. The rule and example now agree; discussion of a work-related tax burden without a policy-change demand can remain work. |
| Medium | Some retained answers may not include every tag the broadened rules now support. | Agreement with the retained answers is not identical to following v4 faithfully. | Keep approved labels. Classify disagreements as possible reference/rule mismatch, unsupported inference, model error or output-limit omission. No automatic relabeling. |
| Medium | The two-tag limit necessarily misses some accepted tags. | Missing a third topic need not mean the model failed to recognize it. | Keep the limit for comparability. Report the theoretical limit and inspect the five three-tag cases separately. |

The inherited request wrapper also says to apply **version 3**. When preparing the new experiment, use the correct version in each arm and keep the same output-schema instructions in both. This is a request-construction requirement; the new runner has not been built or tested yet.

## Ongoing-war vigils

The requested clarification is now explicit. A vigil about an ongoing war is not automatically culture because it remembers victims. Its subject can be international politics and human rights. An actual singing, dancing or storytelling program can additionally support culture even while the issue is ongoing. The event purpose decides; there is no age cutoff.

The rubric includes contrasting invented examples for an ongoing-war/civilian-protection vigil and historical storytelling. Historical narration alone does not automatically establish a current international-affairs topic.

## Deliberate choices to test

Civic colorful/diverse language as an LGBTQ signal, physical expansion as an environmental subject, public peace appeals, humanitarian protection and religious subjects are intentional project choices. The reviewer does not recommend removing them merely because another taxonomy might differ.

These broad rules can also add extra tags or push another correct tag out of a two-tag response. Inspect such tradeoffs. Learned knowledge is allowed, but a remembered association is not independent verification of one event's organizers or demands.

## Limits of the comparison

The reference contains **24 one-tag, 25 two-tag and five three-tag cases**, totaling **89 tags on 54 demonstrations**. With at most two correct predictions per case, even a perfect model can recover only **84 of 89 tags: 94.4% recall**. Its maximum exact-set match is **49/54 = 90.7%**; maximum micro F1 is **97.1%**. These are mathematical ceilings, not measured results or reasons to lower the 80/80/95 targets.

The same familiar cases helped shape the rules. A higher score after revision would be development evidence. It would not prove that the new rules or model generalize to unseen events. Keep all 54 approved cases in the primary comparison and retain the original-reference view.
