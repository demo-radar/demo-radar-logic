# Current tagging rules — rubric-v3 operational rendering

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

## Scope precedence

**Revised scope decision:** `politics` means German domestic politics. `international-politics` combines the old conflict scope with foreign political affairs, including elections and political prisoners abroad. A protest about Iran at its embassy or a political demonstration for/against Israel falls under `international-politics`; add `human-rights`, `lgbtq`, or another tag when the actual demand supports it. Embassy location alone is insufficient. A demonstration about antisemitism in Germany is not automatically international politics. Judge the subject without endorsing a position. This supersedes the earlier country-neutral politics rule.

## Development-review decisions — 1 October 2026 (rubric-v3)

- Opposition to German parties or right-wing extremism supports `politics`. Add `human-rights` when antiracism or a rights demand is explicit; party opposition alone is insufficient.
- Basic income is `social-issues`; add `work` when the event explicitly discusses how income security changes the choice or meaning of work.
- A demand for a place for homeless people is `social-issues` when helping that group is the central subject. A distinct housing-policy demand can also support `housing`.
- Allegations of violence can be tagged by their stated subject without verifying the allegations. `politics` still requires a German political subject; mentioning Germany alone does not establish it. A retained reviewer assignment that depends on unstated background must record that limitation.
- Later events, party organizers, rainbow imagery or the word colorful do not alone verify a specific earlier event's demands. Preserve accepted development answers with explicit source or rule limitations where those demands are not established.
