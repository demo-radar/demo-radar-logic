# Three rubric boundaries — proposal for review

**DR-70 · 7 October 2026 · Policy decisions recorded; v4 remains active**

V4 remains the active benchmark. R2 and R3 are approved amendments for a possible v5. R1 is superseded by the approved separate remembrance purpose below. This is not a complete or active v5 rubric. No notebook loads this file. The purpose is a consistent tagging policy, not a higher score obtained by changing answers to match models.

## The three decisions

| Rule | Proposal | Effect |
|---|---|---|
| R1 — Remembrance purpose | Record remembrance separately from topic tags, with no minimum age. | Replaces the earlier proposal to automatically combine remembrance with culture; topics still need supporting evidence. |
| R2 — Religious context | Religion needs a religious purpose or subject. Identity, greetings, ownership and nearby buildings alone are insufficient. | Narrows v4's broad references to religious institutions, places and figures. |
| R3 — Main purpose | Tag central demands and actual programs. A setting, passing phrase or means of participation does not automatically add a topic. | Clarifies public space, charity runs and cultural programs while allowing multiple central topics. |

These proposals can change meaning and reference labels. They are not merely spelling edits. Consider consequences that could lower either model's score too.

## R1 — Remembrance as a separate event purpose

**Decision: approved by the reviewer on 7 October 2026.** This supersedes the original R1 proposal. `remembrance` describes an event's purpose alongside its topic tags; it is not a thirteenth topic and does not consume a topic suggestion slot.

**Definition:** An event whose central purpose includes remembering or honoring people who died, victims, or a significant past event. There is no minimum time since the event. Remembrance may concern an ongoing conflict or unresolved incident and may coexist with protest, demands for accountability or prayer.

Classify the purpose, not the age. Mentioning a death, anniversary or past event does not alone establish remembrance. Historical information alone is also insufficient.

| Example | Remembrance? |
|---|---|
| Gathering to remember victims of October 7 | Yes, even while the wider conflict continues. |
| Vigil honoring a student killed in an explosion | Yes, whether yesterday or years ago. |
| Protest demanding an investigation into an explosion | Only if honoring victims is also a central purpose. |
| Demonstration demanding a ceasefire | Not automatically; a remembrance purpose must be established. |
| Historical lecture about an old building | Not automatically; sharing history is not necessarily commemoration. |

Remembrance does not automatically add `culture`, `human-rights` or `religion`. Remembering persecution can support human-rights from the subject; an accidental death does not establish a rights issue on its own. A prayer purpose can support religion. Historical learning or an actual cultural program can support culture. Interpret the title, supplied evidence and relevant learned knowledge together; do not infer unsupported details.

**Implementation boundary:** approval establishes the concept, not a deployed field. The current data schema, model responses, topic catalog and benchmark remain unchanged. A later implementation needs a separate field definition, reviewed examples and an evaluation of purpose detection. Do not retroactively add it to existing topic scores. The current v4 culture wording remains part of the preserved v4 benchmark; the new distinction belongs to future versioned policy.

## R2 — Religious references and religious purpose

**Proposed wording:** Use `religion` when faith, worship, religious teaching, religious practice, religious food rules or the ability to use a religious institution for those purposes is a central subject. A prayer gathering, a demand for kosher provision or a peace event centered on religious teaching qualifies.

Do not add `religion` solely because a group has a religious identity, the title includes a religious greeting, a building has a religious owner, a religious figure is quoted, or a religious site is nearby. Opposition to discrimination against a religious community supports `human-rights`; add `religion` when worship, belief or another religious purpose is also central. Apply the same distinction to every faith.

For historical tours, classify the tour's purpose. A tour about persecution and memorials can receive `culture` + `human-rights` without `religion`. A tour about religious traditions can also support `religion`. A community's name alone does not establish religious content.

| Invented example | Decision at this boundary |
|---|---|
| “Gemeinsames Gebet für Frieden” | `religion` is central; other topics follow the existing rules. |
| “Erinnerungsweg zu den Opfern religiöser Verfolgung” | `remembrance` is the purpose; persecution supports `human-rights`. Add `culture` for historical learning and `religion` only for a central religious subject beyond identity. |
| “Koschere Mahlzeiten in der Gemeinde ermöglichen” | `religion`: religious dietary practice is the subject. |
| “Tierwohl auf Höfen eines kirchlichen Unternehmens” | `environment`; church ownership alone does not add `religion`. |

**Consequence to consider:** this could remove religion from a historical-community tour even when both models previously suggested it. It also narrows v4's treatment of institutions. The change must be explicit.

**Decision R2: approved by the reviewer on 7 October 2026.** This approves the proposed boundary; v4 and saved reference answers remain unchanged.

## R3 — Central topics, setting and event format

**Proposed wording:** For each tag, identify the demand, purpose or actual program that supports it. A topic can be central without appearing as an exact keyword. Keep multiple topics when each is independently supported.

Public space supports `housing` when its use, access, allocation, development or neighborhood design is itself central. A general wish for safer public space alongside another policy demand is insufficient on its own. A specific proposal to change how that space is used may support housing as an additional topic. A road-safety purpose remains `mobility`.

A run, walk or bicycle procession used to promote another cause does not automatically receive `culture`. Sport qualifies when sport itself or a substantive sporting program is a purpose. An organized dance, singing or storytelling program still supports `culture`, including when it expresses another cause; incidental background music does not. This preserves v4's inclusion of actual cultural programs.

Inclusion supports `human-rights`. Care or support for people facing illness or hardship can also support `social-issues`. Neither excludes the other. A general community gathering or appeal to togetherness does not establish social care by itself. When no topic is supported by the available information, an empty model answer can be appropriate; that does not establish that a context-assisted reference is false.

| Invented example | Decision at this boundary |
|---|---|
| “Suchthilfe ausbauen, Drogentote verhindern und die Drogenpolitik reformieren; für sichere Plätze” | `social-issues` + `politics`; the general public-space benefit alone does not add `housing`. |
| “Den Stadtplatz als frei zugänglichen Treffpunkt erhalten” | `housing`: public-space access and use are central. |
| “Solidaritätslauf für Teilhabe und Unterstützung schwerkranker Menschen” | `human-rights` + `social-issues`; the word run alone does not add `culture`. |
| “Tanzveranstaltung mit gemeinsamem Gesang für den Frieden” | An actual cultural program supports `culture`; other central topics still qualify. |

**Decision R3: approved by the reviewer on 7 October 2026.** This approves the proposed distinctions; v4 and saved reference answers remain unchanged.

These examples isolate the proposed boundaries; they are not exhaustive answers for every possible context. Apply unchanged v4 rules to other topics.

## Earlier consistency check

The private table checks **15 reviewed cases**: ten relevant to these boundaries, plus five controls where both models matched the reference. The ten boundary cases include agreements and disagreements. Codex inspected the evidence and rules after model outputs were known. This is not a new prediction test or independent reference-label review.

- The earlier R1 check concerned the superseded topic-overlap proposal. It does not validate the newly approved separate remembrance purpose.
- R2 affects both a rejected religion prediction and an existing historical-tour reference. Prayer-based religion remains supported.
- R3 accepts care plus inclusion, retains an actual dance program and separates a public-space benefit from a public-space demand.
- One fully matching remembrance case remains purpose-dependent: an anniversary alone cannot settle historical learning versus current advocacy. Model/reviewer agreement is not used as proof.
- The five controls retain their supported topics under this inspection. This does not predict model behavior with a changed prompt.

Private detail: `reports/fresh-confirmation/2026-10-07/comparison-v1/audit-review/boundary-impact-v1.md`. No additional sources were retrieved; evidence gaps remain unresolved.

## Next steps

R1 is resolved through the separate remembrance purpose; R2 and R3 are approved. DR-70 is Done on Jira, closed by the reviewer. Continue to [DR-27's service recommendation](../plan/service-recommendation.md), with DR-24 accounting alongside it. No repeat labeling is needed for these policy decisions.

Keep v4 active for reproducibility. Consolidating future policy, implementing purpose detection or changing reference answers requires an explicit versioned change; it is not part of the current scored configuration. Reference changes must be recorded separately from model improvements.

Paid optimization is paused. The 80% precision, 80% recall and 95% coverage targets remain fixed. An untested v5 cannot replace v4 on a quality claim. Any later comparison needs the same approved answer key and explicit regression criteria. Cases that shaped these changes are development evidence.

Evidence: [DR-69 audit](../audits/2026-10-07-fresh-v4-run-audit.md), [v4 rubric](tagging-rubric-v4.md), [fresh results](../results/fresh-v4-confirmation.md).
