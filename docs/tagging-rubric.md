# Topic-tagging rubric — version 3

Personal provenance is redacted in this public copy. Exact historical input bytes
and their hashes belong to the [original research revision](research-replay.md).
This file is not the deployed v4 rubric.

A **reviewer** is the person checking labels or approving suggestions. See the
[review terminology](methodology.md#review-terminology); it is not a separate
role from the earlier term “human annotator”.

**Current version:** rubric-v3 records the five development-review decisions accepted on 1 October 2026 (DR-46). It clarifies antiracism, homelessness support and basic income. The catalog remains taxonomy-v2 with the same 12 tags. Earlier reviews retain their recorded versions; affected final references must be reviewed independently before final inference. The rubric-v2 approval history below is preserved.


**Status:** The reviewer approved **rubric-v2** on 1 October 2026 during the development-data review (DR-43). It clarifies Pride/human-rights and German legislation/politics overlaps. Tag catalog **taxonomy v2** still has the same 12 slugs; no new tag or production migration is needed. Rubric-v1 was approved on 28 September and remains the recorded reference for earlier reviews and experiments. Existing final-test labels are not automatically upgraded to v2; review affected cases before claiming a v2 final comparison.

**Pilot update, 25 September 2026:** the reviewer confirmed the saved 40 development examples. Some choices differ from the definitions below. Preserve those decisions and their disagreements in the private daily audit rather than silently changing either the labels or the rules. The pilot is reviewed development data, not proof that the rubric is fully consistent. Use the current written definitions for subsequent labeling. The approved v2 changes are recorded below; older decisions retain their original rubric version until explicitly reviewed.

This rubric defines taxonomy **v2** for the DemoLogic comparison and the planned Demo Radar catalog migration. It has 12 topic slugs: `international-politics` replaces `conflict`, while `politics` is narrowed to German domestic politics. Existing v1 snapshots remain historical inputs until explicitly migrated and reviewed. See the [migration guide](taxonomy-migration.md).
The examples below are synthetic. The 40-record development pilot informed rubric-v1; the DR-43 review informed the v2 overlap changes. Historical production tags remain training data; they are not automatically the answer key. Use the written rules below for final-test review. Retained pilot disagreements do not add unwritten exceptions to the rubric. A later change in meaning requires a new rubric version and review of affected labels.

## How to choose tags

1. **Find out what the demonstration is about.** Read its title and available source text. If a name or phrase is unclear, check a reliable source and keep the link. The event's date, location, route, or organizer can help identify it, but these details alone do not tell us its topic.
2. **Choose the main topic or topics.** Add a tag only when the demonstration clearly concerns it. For example, “more bike lanes” supports `mobility`; it does not also need `politics` just because protesters ask the city government to act. Demo Radar currently stores up to two topic tags. Reference labels may contain three or more equally central, evidence-supported topics; explain each in the private notes. The comparison's tie rule is defined below.
3. **Do not guess when the topic is unclear.** Check the available evidence. If it still does not tell us the topic, mark the case **unclear**. If the topic is clear but none of the 12 tags fits, mark **no matching tag**. These are different situations. Demo Radar's `other` tag is a fallback and is not part of this 12-tag comparison.
4. **Use the same rules throughout the comparison.** Label final-test demonstrations before looking at any model suggestions, and record which version of this rubric you used. The support page may display more candidate tags than the two that can be saved; showing a candidate does not make it an approved tag.

## The 12 current topic tags

The following definitions describe taxonomy v2. Historical assignments are not assumed to meet these boundaries merely because their slug has been migrated.

| Tag | Include when the central subject is… | Do not use merely because… | Synthetic example |
|---|---|---|---|
| `environment` — Umwelt / Environment | Climate, energy transition, nature, animals, water, or environmental protection. | The march passes through a park or uses bicycles. | “Für den Schutz der Stadtbäume” → `environment`. |
| `mobility` — Verkehr / Mobility | Roads, cycling, walking, public transport, traffic policy, or transport infrastructure. | Participants travel by bicycle or the route closes a road. | “Sichere Radwege jetzt” → `mobility`. |
| `housing` — Wohnen / Housing | Rent, housing supply, eviction, urban development, public space, or neighborhood development. | The event happens in a residential area. | “Bezahlbare Mieten im Kiez” → `housing`. |
| `work` — Arbeit / Work | Jobs, wages, working conditions, strikes, unions, collective bargaining, or basic-income demands explicitly discussing the meaning or choice of work. | People volunteer to organize the event. | “Tarifvertrag für Reinigungskräfte” → `work`. |
| `social-issues` — Soziales / Social Issues | Poverty, welfare, homelessness, healthcare access and funding, social care, support services, or protection from violence. | The event concerns another policy area that also has social consequences. | “Gesundheitsversorgung für alle sichern” → `social-issues`. |
| `education` — Bildung / Education | Schools, universities, childcare, research, or educational access. Healthcare access belongs under `social-issues` in this benchmark. | A school or university is only the meeting place, or the event concerns healthcare without an educational demand. | “Mehr Kitaplätze für alle” → `education`. |
| `lgbtq` — LGBTQ+ | Queer rights, visibility, Pride, or trans, inter, lesbian, gay, or bisexual concerns. Pride and LGBTQ equality or rights also support `human-rights`, as explained below. | A queer organization supports an otherwise unrelated cause. | “Für trans Rechte und Sichtbarkeit” → `lgbtq`. |
| `international-politics` — Internationale Politik / International Politics | Political affairs of other countries, international relations, foreign policy, war, peace, humanitarian crises, or political repression abroad. | An embassy is nearby, participants have a foreign nationality, or the title uses another language. | “Freiheit für politische Gefangene in China” → `international-politics` + `human-rights`. |
| `human-rights` — Menschenrechte / Human Rights | Human or civil rights, antiracism, migration, equality, accessibility, or inclusion, including Pride and LGBTQ equality or rights. | The text uses a generic appeal to fairness, opposes a German party, or opposes right-wing extremism without an explicit antiracism or rights demand. | “Gegen Abschiebungen” → `human-rights`. |
| `politics` — Deutsche Politik / German Politics | German domestic elections, parties, government institutions, democratic processes, public administration, political representation, or a German bill/law that the protest explicitly seeks to pass, change, or oppose. | The demonstration is in Germany or addresses German officials about another topic. German foreign-policy demands belong under `international-politics`. | “Reform des deutschen Wahlrechts” → `politics`. |
| `culture` — Kultur / Culture | Arts, media, history, commemoration, cultural institutions, or sport. | Music or a performance is simply part of a protest about another subject. | “Erhalt des Nachbarschaftskinos” → `culture`. |
| `religion` — Religion | Religious practice, faith communities, belief, worship, or religious institutions as the subject. | A church, mosque, or synagogue is only the meeting point. | “Für den Erhalt eines Gebetsraums” → `religion`. |

## Common overlaps to settle consistently

| Possible overlap | Rule in rubric-v3 |
|---|---|
| `mobility` + `environment` | Use both only when transport **and** environmental effects are explicit central subjects. A road-safety protest is `mobility` alone; opposition to a highway explicitly for climate and traffic reasons can be both. |
| `housing` + `social-issues` | Rent, eviction, housing supply and urban-development policy point to `housing`. Support for homeless people, including provision of a place to live, points to `social-issues` when the central demand is help for that group. Add `housing` only for a separate central demand about rent, supply, eviction or urban development; the word housing alone is insufficient. |
| `work` + `social-issues` | A care workers' wage strike points to `work`. Access to care or support services points to `social-issues`. Basic-income demands explicitly connecting income security with what people would choose to work on receive both tags. Otherwise, both require separate central subjects. |
| `education` + `social-issues` | **Decision, 25 September 2026:** healthcare access, funding, care, and clinics belong under `social-issues`. Use `education` for a separate educational demand, such as medical training. This benchmark rule does not change the production catalog; historical labels may need review. |
| `politics` + another tag | Addressing the government is not enough for `politics`. Add it when elections, institutions, parties, democratic governance, or a specific German bill/law are central to the protest. An accessibility camp focused on a bill’s reading and vote receives `human-rights` + `politics`. A general demand for accessible buildings receives `human-rights`; it does not need `politics` merely because officials can act. |
| `lgbtq` + `human-rights` | Pride and demonstrations for LGBTQ equality or rights receive `lgbtq` + `human-rights`. No separate rights demand is required: the rights celebration or demand itself supports both tags. This does not add `human-rights` to every LGBTQ-related event, nor either tag merely because a queer organization participates. |
| `international-politics` + another topic | International political context and a specific issue may both be central. Political prisoners abroad support `international-politics` + `human-rights`; a protest against a foreign government's anti-LGBTQ+ law supports `international-politics` + `lgbtq` + `human-rights`. Keep all three supported reference tags even if a model can return only two. Housing or labor abroad can receive a second topic tag when the political context and that demand are explicit. Do not automatically add a second tag to every international event. |
| `politics` + `international-politics` | Use both only when separate German domestic and international political demands are central. German arms exports alone are foreign policy, so use `international-politics`, not both. |
| `culture` + `religion` | A religious venue or cultural program alone does not establish the event's topic. Tag the actual demand, and use both only when both are subjects. |

## How version 1 was prepared

The reviewer reviewed 40 development demonstrations and confirmed the saved choices on 25 September 2026. The pilot clarified healthcare, domestic and international politics, and the treatment of equally central topics. Some accepted pilot choices still differ from the written rules; these remain documented development-data limitations. On 28 September, the reviewer approved the written rules as rubric-v1 for final-test labeling.

Record the rubric version actually used and its document fingerprint with the private reference labels. Use that same reference version for every candidate in the final comparison. If a definition must change, record the reason, issue a new rubric version, and revisit affected labels. Do not change the answer key merely to agree with model predictions.

The private pilot log and event-level decisions are not part of this public document.

## Decisions from the pilot — 25 September 2026

**Revised scope decision:** `politics` means German domestic politics. `international-politics` combines the old conflict scope with foreign political affairs, including elections and political prisoners abroad. A protest about Iran at its embassy or a political demonstration for/against Israel falls under `international-politics`; add `human-rights`, `lgbtq`, or another tag when the actual demand supports it. Embassy location alone is insufficient. A demonstration about antisemitism in Germany is not automatically international politics. Judge the subject without endorsing a position. This supersedes the earlier country-neutral politics rule.

**Retain qualifying ties at second place.** The agreed comparison policy normally recommends up to two tags. When additional tags have exactly the same score as the second-ranked tag and pass the model's recommendation threshold, retain all of them. Scores of 0.90, 0.80, and 0.80 therefore produce three recommendations if all qualify. Equal low scores below the threshold produce no recommendations. Compare unrounded scores within the same model and run; near-ties are not ties under this initial policy. Models without scores must record that the numeric tie rule is unavailable rather than invent scores. This documents the evaluation policy; implementing it and changing the production save limit are separate work.

Reviewer reference labels are chosen from evidence before seeing model scores. When three or more topics are equally central and supported, retain those labels and explain each in the notes. Equal reviewer uncertainty scores alone do not establish that a tag fits. Evaluate the tie-inclusive policy and a strict two-tag variant separately against the same full reference labels; do not truncate the answer key to favor either policy. More predictions can improve recall and reduce precision, so report both measures and the number of events receiving more than two recommendations.

## Approved overlap changes — 1 October 2026

the reviewer approved two changes during DR-43: Pride celebrates human rights and can receive both `lgbtq` and `human-rights`; an accessibility protest focused on a German bill’s debate or vote can receive both `human-rights` and `politics`. These decisions change label meaning, so this is rubric-v2 rather than a wording-only edit. The 12 tag slugs are unchanged. Earlier rubric-v1 is preserved in the private research archive at commit `81f4bcecfd00ba17393d7cba73861258efce14ee`.

Review the affected development examples using these written rules, including neighboring categories and events about German legislation. Preserve the original labels and results; record approved changes in a new reference version. Score every candidate against the same version. Rescoring saved predictions changes the measurement, not the model. Retraining or changing prompts is a separate experiment.

For the final comparison, review only the potentially affected held-out answers against the approved rules before looking at final-test predictions. Do not use those answers to choose models, prompts, or thresholds. Record the revision and unresolved cases; do not describe a mixed v1/v2 answer key as a completed v2 reference.

## Development-review decisions — 1 October 2026 (rubric-v3)

- Opposition to German parties or right-wing extremism supports `politics`. Add `human-rights` when antiracism or a rights demand is explicit; party opposition alone is insufficient.
- Basic income is `social-issues`; add `work` when the event explicitly discusses how income security changes the choice or meaning of work.
- A demand for a place for homeless people is `social-issues` when helping that group is the central subject. A distinct housing-policy demand can also support `housing`.
- Allegations of violence can be tagged by their stated subject without verifying the allegations. `politics` still requires a German political subject; mentioning Germany alone does not establish it. A retained reviewer assignment that depends on unstated background must record that limitation.
- Later events, party organizers, rainbow imagery or the word colorful do not alone verify a specific earlier event's demands. Preserve accepted development answers with explicit source or rule limitations where those demands are not established.

These clarifications change meaning and therefore create rubric-v3. Historical predictions retain their original prompts and reference versions. Rescoring them under new answers does not show how a changed prompt would perform. The completed twelve-case development review also contains retained decisions that do not fully follow the written rule; document those cases rather than treating all reviewed answers as independently verified.
