# Topic-tagging rubric — version 4

**Status:** review decisions incorporated under DR-66, 6 October 2026. This is the v4 policy for the next development comparison. Taxonomy v2 and its 12 tags are unchanged. [Version 3](../tagging-rubric.md) remains the exact historical input used by older notebooks. The [change record](v4-review.md) explains the broader definitions and the single approved reference change. The phrase “emotions topics” under mobility has a provisional interpretation, explicitly noted below.

This is a policy for tagging demonstration topics. It does not assess whether a demonstration's claims are true, whether its position is desirable, or whether a participant belongs to a particular group. Humans and models should apply the same topic definitions.

## 1. Decide what the event is about

1. **Identify the main demands or purposes.** Include both support and opposition: opposing construction can still concern `housing`. An event can have several central topics.
2. **Distinguish a topic from its setting or format.** A bicycle procession is not automatically about transport. A hospital location is not evidence of a pay dispute. An organizer's identity does not establish every demand.
3. **Apply the definitions and overlap rules together.** The examples below show complete reference answers for their invented titles. They are not keyword rules.
4. **Keep uncertainty visible in human review.** When one topic is supported but another is uncertain, keep the supported topic and note the unresolved one in the review record. When no topic can be determined, record `unclear`. Use `no_matching_tag` only when the topic is understood and none of the twelve tags fits. Neither status is a topic tag.

**For the planned tags-only model response:** return only the permitted JSON `tags` field, containing supported topic slugs. Return `{"tags": []}` when no tag is supported. Do not add status words, uncertainty fields or explanations to that response. An empty list does not tell us whether the model was uncertain or found no matching category; the current interface cannot distinguish those reasons.

A central topic is a demand, purpose, or recognizable issue established by the title, supplied context or relevant learned knowledge. It does not have to appear as an exact keyword. Interpret slogans and named subjects in context. When several meanings remain plausible, record the uncertainty rather than treating an association as a verified fact.

## 2. Use knowledge and context carefully

The complete rubric is part of the input. **Use the title, supplied context and knowledge learned during training. You are not restricted to literal words in the title.** Learned knowledge can explain names, campaigns, slogans, institutions, laws, religious figures and historical or political context. Use it to infer relevant topics when the connection is well supported. A model does not directly look up its training records, and its memory of a specific event may be wrong or outdated.

Distinguish three sources of information:

| Information | How to use it |
|---|---|
| Title and supplied event description | Direct evidence of the stated subject; an allegation can be classified without being endorsed. |
| Knowledge learned during training | Interpret and connect known subjects, including meanings not spelled out in the title. Distinguish a supported interpretation from an uncertain association; do not invent facts to fill a gap. |
| External event source | Use its demands when the event identity matches. Check date and identifying details where available. A similar or later event is background, not proof about this one. |

**Search off still allows learned knowledge.** It only means no live web retrieval. Models should combine their learned knowledge with the title, supplied context and this rubric. With search on, they may also obtain current sources. A model should not claim to have checked a website unless retrieval actually occurred. Humans may search when their task allows it; report unequal access to sources as a limitation.

## 3. The twelve tags

| Tag | Include | Exclude when it is only… |
|---|---|---|
| `environment` | Climate, carbon emissions, energy transition, nature, animals, water and environmental protection. Opposition to data centers or major physical company expansion also belongs here when the development footprint is the subject. | A company name without an expansion/environmental subject, or merely meeting in a park. |
| `mobility` | Streets, road use, speed limits, cycling, walking, public transport, traffic policy, road safety and transport infrastructure. Traffic-related fear or stress can qualify when travel or road safety is the subject. | A street address, the way participants travel, or a temporary road closure without a transport subject. |
| `housing` | Rent, housing supply, eviction, urban development, public space and neighborhood development. Public-space protection can overlap with environment. Support for or opposition to development both qualify. | A residential location, or immediate help for homeless people without a separate housing-policy demand. |
| `work` | Jobs, staffing levels or limits, wages, working hours, overtime, workplace training limits, employment-related tax burdens, strikes, collective bargaining and labor representation. Basic income also qualifies when the choice or meaning of work is central. | A profession, union organizer or workplace location without a work-related subject; tax questions unrelated to work. |
| `social-issues` | Poverty, welfare, homelessness, healthcare access or funding, social care, support services and protection from violence. | A general appeal to social justice with no specific social demand. |
| `education` | Schools, universities, childcare, research, educational activities and access, where the educational system or learning is the subject. | A campus location or the word university without a demand or activity concerning education. |
| `lgbtq` | Queer rights, visibility, Pride, and trans, inter, lesbian, gay or bisexual concerns. Civic slogans about colorful, diverse or rainbow communities may signal LGBTQ inclusion even without an explicit identity word. | Literal colors, biodiversity, animal diversity, or an unrelated cause merely supported by a queer organization. |
| `international-politics` | Affairs or situations in other countries, support for or opposition to a country, foreign policy, war, peace, humanitarian crises and repression abroad. Political controversy around a foreign-linked institution can qualify through context. | A foreign word, nationality or location with no international public-affairs subject. |
| `human-rights` | Human and civil rights, antiracism, migration, equality, accessibility, inclusion, humanitarian aid and protection of civilians, including humanitarian demining. Pride and LGBTQ rights/equality also qualify. | Generic fairness, party opposition, animal welfare or every social problem. |
| `politics` | Calls for domestic political action in Germany, democracy and its protection, elections, parties, institutions, public administration, political accountability and legislation. A specific politician or law need not be named. | A German location alone, a topic with only indirect political consequences, or foreign affairs alone. |
| `culture` | Arts, media, history, historical remembrance, cultural institutions, sport and an actual cultural program such as singing, dancing or storytelling. | A current-event vigil without a cultural purpose/program, incidental background music or a participant’s cultural profession. |
| `religion` | Religious practice, belief, communities, institutions and places as subjects; religious food practices such as kosher; Jesus, prophets, clergy and other religious figures when relevant to the event. | A neutral meeting point at a religious building, incidental food or a name without a religious meaning in context. |

## 4. Resolve common overlaps

### German and international politics

Use `politics` for a recognizable call for political action in Germany. This includes protecting democracy, opposing domestic extremism or antisemitic hostility, seeking political accountability, and requesting state action against harmful practices. A specific politician, law or institution need not appear in the title. Use learned knowledge to interpret the civic demand. This broadens the earlier rule requiring a more explicit domestic political subject.

Do not add `politics` merely because all policy subjects could involve officials. A request about transport, housing or healthcare can remain under its topic tag when no political-action purpose is expressed or reasonably established by context. A company dispute alone is not a call for domestic political action.

Use `international-politics` when the public-affairs subject concerns another country, support for or opposition to it, or war and peace beyond the current domestic German situation. Public peace appeals can qualify without naming a war or country. Personal harmony alone is not an international subject. German foreign policy and arms exports also belong here.

Political controversy about a foreign-linked cultural institution can support `international-politics`; it is not limited to formal diplomacy. A foreign cultural name without such context is insufficient. Use both political tags when domestic and international subjects are central. Criticism of Israel or another country can be international; antisemitism in Germany is not automatically about that country. Do not infer every participant's position from a slogan.

### Human rights, LGBTQ and social issues

Pride and LGBTQ equality or rights receive `lgbtq` + `human-rights`. A cultural LGBTQ focus or an inferred civic-diversity association alone does not automatically add `human-rights`; apply the rights definition separately.

**Colorful and diverse are contextual signals, not forbidden words.** A civic slogan such as a city staying colorful, making streets diverse, or welcoming all colors in the armed forces can reasonably signal LGBTQ inclusion. Use the full subject and learned cultural/political associations. These words are not universal synonyms for LGBTQ: colorful animals, biodiversity, paint colors, or an animal-rights campaign do not qualify merely because they use them. This is the project's chosen interpretation policy; it does not prove an organizer's intended meaning in every case.

Accessibility is `human-rights`. Add `politics` when political action or a German legal/governance demand is central. Healthcare access and funding are `social-issues`; add `work` when staffing, jobs, pay, training conditions or working hours are a central subject established by the title or relevant context.

Protection from violence can support `social-issues`. Add `human-rights` when equality, discrimination, civil liberties or another rights issue is central. Allegations can be classified by their stated subject without endorsing their truth. Inferred demands for domestic political accountability may support `politics`; that tag does not verify the allegation or government involvement.

Humanitarian aid, humanitarian demining and protection of civilians fall under `human-rights` in this project. Add `international-politics` when war, recovery from conflict or an international humanitarian situation is central. The approved definition is broader than the earlier v3 wording.

### Transport, public space and environment

Streets, speed limits and road safety are mobility topics. When environmental effects such as transport emissions are also central, use `mobility` + `environment`. A street address is only a location unless street use itself is the subject.

**Provisional wording:** “emotions topics” is interpreted here as fear, stress or anger connected to traffic or road safety. The intended phrase has been asked about; unrelated emotions do not receive `mobility`.

Opposition to the physical expansion of a data center or major company can concern `environment` through land, water, energy or carbon impacts, even when every effect is not spelled out. Do not invent an emissions figure or site-specific harm. A labor dispute with that company remains `work` unless expansion/environment is also central.

Public space can receive `housing` + `environment` when land use, neighborhood development or access to space overlaps with environmental protection. For example, protecting a green public area from development can support both. Public-space use alone does not require an environmental tag, and a park meeting place does not establish either topic.

### Housing, welfare, work and education

Rent, eviction, housing supply and urban development support `housing`, including opposition to building. Immediate help for homeless people supports `social-issues`; add `housing` for a separate central housing-policy demand.

Staffing caps or shortages, overtime, working hours, workplace training restrictions and tax burdens connected to employment or professional work support `work`. Add `politics` when the demand is to change German tax policy, such as reducing taxes for healthcare workers. The policy-change demand itself establishes the political subject; it need not name a politician or law. Discussing a work-related tax burden without demanding or otherwise establishing a policy change can remain `work`. Basic income is `social-issues`; add `work` when income security and the choice or meaning of work are central.

Workplace training conditions are `work`. Add `education` when educational provision, access or the learning system is itself central. Healthcare funding is `social-issues`, not `education` merely because a university hospital is involved.

A university setting is not an educational demand. A slogan such as “No justice without peace on campus” does not establish what the educational system should change. Classify the actual peace/justice subject; add `education` only when teaching, research, educational activities or access is a subject too.

For this catalog, historical storytelling, cultural interpretation or a remembrance tour alone belongs to `culture`. Do not add `education` just because participants can learn from it. Add `education` when educational provision, access, teaching, research, training or the learning system is a distinct central subject.

### Culture, current-event vigils and religion

Singing, dancing, storytelling and other actual cultural programs support `culture`, including programs used to express another cause. Incidental background music or the cultural profession of participants is not enough. Historical remembrance and learning can also support `culture`. Historical narration of a past war alone does not establish a present foreign-affairs subject. Add `international-politics` when the event also addresses a war, peace or international public-affairs issue, rather than merely recounting history.

A vigil about a current event, victim, ongoing war or demand for accountability is not automatically `culture`, even if its title says memory or remembrance. Tag the issue it addresses. For example, a vigil demanding an end to an ongoing war supports `international-politics`; add `human-rights` when civilian protection or rights are also central. Add `culture` when there is an actual cultural program or a historical-learning purpose. An issue can be ongoing and still have a cultural program, so ongoing does not forbid `culture`. There is no fixed age cutoff: the event’s purpose decides.

Religious sites as subjects, kosher or other religious food practices, Jesus, prophets and religious personnel can support `religion`. A peace gathering centered on religious teaching or figures may receive `religion` + `international-politics`; the religious subject need not be a separate demand. Merely using a church as a neutral meeting place remains insufficient. Culture and religion can both qualify when an actual cultural program and religious subject are present.

### Multiple topics

Keep every supported central topic in the human reference, even if there are three or more. Apply the same standard to each; uncertainty is not a reason to list all possibilities.

The experiment separately specifies how many suggestions a model can return. For the next comparison, retain the strict two-tag output setting used in DR-65 so that a new output limit does not obscure the rubric effect. Reference answers remain complete. Numeric ties and the separately tested qualitative third-tag policy do not change this experiment's output setting.

## 5. Complete examples and contrasts

These are invented teaching examples. They are not the 54 reviewed titles or their answer key. Reference answers show all supported topics; a model output cap may prevent returning all of them.

| Invented title | Complete reference tags | Why |
|---|---|---|
| Für trans Rechte und Sichtbarkeit | `lgbtq`, `human-rights` | Explicit rights and visibility; the old single-tag example was incomplete. |
| Sichere Querungen für Kinder | `mobility` | Road safety; no separate education or environmental demand. |
| Gegen Tierversuche, für den Schutz der Tiere | `environment` | Animal welfare does not imply human rights. |
| Gegen die AfD bei der nächsten Wahl | `politics` | German party and election; no separate rights demand. |
| Gegen die AfD und gegen rassistische Ausgrenzung | `politics`, `human-rights` | Adds explicit antiracism. |
| Mehr Mittel für die Versorgung kranker Menschen | `social-issues` | Healthcare funding; no labor demand. |
| Mehr Mittel für die Versorgung und bessere Arbeitsbedingungen in der Pflege | `social-issues`, `work` | Adds an explicit staff demand. |
| Wohnungsvermittlung für Menschen ohne Unterkunft | `social-issues` | Direct support for homeless people. |
| Gegen Verdrängung durch die neue Bebauung | `housing` | Opposition still concerns urban development. |
| Für Barrierefreiheit: das deutsche Gleichstellungsgesetz verbessern | `human-rights`, `politics` | Accessibility plus a specific German legislation demand. |
| Mahnwache gegen Krieg und Waffenlieferungen | `international-politics` | War and arms deliveries; no domestic political demand. |
| Mahnwache: Den laufenden Krieg beenden und Zivilisten schützen | `international-politics`, `human-rights` | Ongoing war and civilian protection; a vigil is not automatically culture. |
| Gedenkveranstaltung mit Erzählprogramm zur Geschichte eines früheren Krieges | `culture` | Historical learning and storytelling; no current political demand specified. |
| Historischer Rundgang zur Geschichte einer alten Bibliothek | `culture` | Historical learning is the purpose. |
| Höhere Honorare für freiberufliche Musikerinnen | `work` | Their pay is the subject, not a cultural program. |
| Stopp der Rechenzentrum-Erweiterung auf der Grünfläche | `environment`, `housing` | Physical expansion and urban green-space development. |
| Tempo 30: sicher und mit weniger Abgasen unterwegs | `mobility`, `environment` | Speed and safety plus emissions. |
| Gegen Personalabbau und unbezahlte Überstunden | `work` | Staffing and overtime. |
| Steuerlast für selbstständige Pflegekräfte in Deutschland senken | `work`, `politics` | A work-related tax burden and a demand to change German tax policy. |
| Selbstständige Pflegekräfte informieren über ihre berufliche Steuerbelastung | `work` | The work-related tax burden is the subject; no demand to change policy is stated or established by context. |
| Mehr Zugang zu Studienplätzen und bessere Lehre | `education` | Educational access and teaching are the subject. |
| Unser Viertel bleibt bunt und vielfältig | `lgbtq` | The approved civic-diversity interpretation can include LGBTQ without an explicit identity word; it is not proof of organizer intent. |
| Bunte Vielfalt für den Schutz der Wildtiere | `environment` | Animal diversity does not imply LGBTQ. |
| Gemeinsames Singen und Tanzen für den Frieden | `culture`, `international-politics` | Cultural program and a public peace appeal. |
| Mahnwache für Aufklärung von Polizeigewalt und gegen Rassismus | `politics`, `human-rights` | Current accountability and antiracism; a vigil alone is not culture. |
| Koschere Verpflegung in der Gemeinde sichern | `religion` | Religious food practice. |
| Friedenskundgebung im Zeichen der Lehren Jesu | `religion`, `international-politics` | Religious teaching and peace are both subjects. |
| Humanitäre Hilfe und Minenräumung für Menschen im Kriegsgebiet | `human-rights`, `international-politics` | Civilian protection and a conflict setting. |
| Gegen ein ausländisches Gesetz, das queere Menschen ihrer Rechte beraubt | `international-politics`, `lgbtq`, `human-rights` | Foreign legislation and explicit LGBTQ rights; retain all three in the reference. |

## 6. Review and versioning

A clearer rule may reveal a problem in a previous human answer. It may also show that the model lacked context available to the reviewer. Do not automatically call either situation a model error.

The 54 reviewed examples are development data used to improve this policy. They remain a selected, repeatedly examined, single-reviewer set. Any scores after revision measure agreement on these examples; they do not independently establish generalization.

Keep original labels, earlier prompts and results. Record changes to meaning and individual reference answers separately. The D1–D5 answers were explicitly retained and only D6 gained a tag. This is a reviewer-defined reference, not an independently verified accuracy estimate. Record the final rubric fingerprint and reference version before inference. Compare saved old predictions and new predictions against the same revised references, retaining an additional view against the original answers. Do not select between answers based on which improves scores.
