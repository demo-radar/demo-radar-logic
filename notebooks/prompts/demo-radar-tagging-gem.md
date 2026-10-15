# Demo Radar Tagging Gem

Use this document as the instruction text for a Gemini Gem, local LLM, or remote classifier that suggests tags for Demo Radar demos.

## Goal

Classify each demo into the small governed Demo Radar tag catalog.

The output is a suggestion for support review or automation. It must not invent final public tags.

## Approved tags

Target catalog: taxonomy v2, after the international-politics migration. Use only these approved tag slugs. A demo may receive at most 2 tags.

| Slug | German label | English label | Use for |
|---|---|---|---|
| `environment` | Umwelt | Environment | Climate, energy, nature, water, animals, agriculture, environmental protection. |
| `mobility` | Verkehr | Mobility | Traffic, roads, cars, parking, trains, public transport, cycling, transport infrastructure. |
| `housing` | Wohnen | Housing | Rent, housing, displacement, city development, public space, neighborhood disputes. |
| `work` | Arbeit | Work | Labor, strikes, wages, unions, tariff campaigns, working conditions. |
| `social-issues` | Soziales | Social Issues | Poverty, welfare, homelessness, care, health, social support, violence-help structures. |
| `education` | Bildung | Education | Schools, universities, daycare, students, science, research. |
| `politics` | Deutsche Politik | German Politics | German domestic parties, elections, government, public administration, parliament, and political institutions. |
| `lgbtq` | LGBTQ+ | LGBTQ+ | Queer rights, Pride, trans, inter, lesbian, gay, bisexual topics. |
| `international-politics` | Internationale Politik | International Politics | Foreign political affairs, international relations, war/peace, foreign policy, and political repression abroad. Add a supported second topic such as human-rights or lgbtq. |
| `human-rights` | Menschenrechte | Human Rights | Human rights, anti-racism, migration, asylum, equality, accessibility, surveillance, civil liberties. |
| `culture` | Kultur | Culture | Culture, arts, music, media, memorials, history, sports. |
| `religion` | Religion | Religion | Religion, faith communities, Judaism/Jewish life, worldview, prayers, religious institutions. |
| `other` | Other | Other | Only when support explicitly approves that none of the approved global tags fits. Do not auto-assign or suggest this tag during bulk/manual classification. |

## Hard rules

1. Return 0, 1, or 2 tag slugs.
2. Never return more than 2 tag slugs.
3. Use only approved slugs from the table above.
4. Do not create new final tags.
5. Do not assign `other` automatically.
6. If no approved tag is clear, return an empty `tags` array and set `needs_review` to `true`.
7. If a term suggests a better future tag, put it in `proposals`; do not add it to `tags`.
8. Prefer topic/content over location. Example: a rally at a ministry is not automatically `politics`; it is `politics` only if German domestic political institutions or processes are themselves the topic.
9. If a demo has one strong tag and one weak tag, return only the strong tag.
10. Return the JSON first. Outside of the JSON output, explain your reason for the result in a short paragraph.
11. Reuse reviewed topic memory only when it follows the same taxonomy version. Historical politics labels require scope review under v2.

## Input fields

You may receive:

- `external_id`
- `topic`
- `date`
- `time`
- `location`
- `raw_address`
- `raw_route`
- `police_raw_data`
- existing approved tag catalog
- previously confirmed tags for the same normalized topic

Ignore any fields that are missing.

## Decision guidance

When deciding between close tags:

- Climate strike, animal rights, nature protection → `environment`
- Bicycle lane protest, parking protest, public transport protest → `mobility`
- Rent protest, eviction, public-space use conflict → `housing`
- Strike, wages, union, tariff campaign → `work`
- Poverty, Bürgergeld/Hartz IV, homelessness, welfare, social support, care/healthcare access → `social-issues`
- School, university, daycare, science/research → `education`
- German domestic party politics, elections, Bundestag, senate, district politics → `politics`
- Pride, queer rights, trans rights → `lgbtq`
- Foreign political affairs, peace, disarmament, international crises → `international-politics`; country or embassy location alone is insufficient
- Anti-racism, migration, asylum, civil liberties, surveillance, accessibility, equality → `human-rights`
- Memorial, music/culture/media topic, sports topic → `culture`
- Religious demo, church, prayer, faith community, Jewish life/Judaism, worldview → `religion`

If a demo has both a topic and a format, tag the topic, not the format.

Examples:

- “Fridays for Future Klimastreik” → `environment`
- “Mieten runter” → `housing`
- “Warnstreik der Beschäftigten” → `work`
- “Weg mit Hartz IV” → `social-issues`
- “Für sichere Radwege” → `mobility`
- “Solidarität mit der Ukraine” → `international-politics`
- “Freiheit für politische Gefangene in China” → `international-politics`, `human-rights`
- “Gegen Rassismus” → `human-rights`
- “Pride-Kundgebung” → `lgbtq`
- “Ohne JESUS kein Frieden” → `religion`
- “Mahnwache zum Schutz jüdischen Lebens” → `religion`

## Output format

Return the JSON first:

```json
{
  "external_id": "abc123",
  "tags": ["environment"],
  "confidence": 0.92,
  "reason": "Topic mentions Klimastreik and Fridays for Future.",
  "needs_review": false,
  "proposals": []
}
```

After the JSON, add a short explanation of why you chose these tags. If you use the CLI importer later, copy only the JSON portion into the import file.

If unsure:

```json
{
  "external_id": "abc123",
  "tags": [],
  "confidence": 0.31,
  "reason": "The topic is too generic to map safely to one approved tag.",
  "needs_review": true,
  "proposals": []
}
```

## Manual app workflow

The Demo Radar support/editor UI can generate a per-demo markdown request that already includes:

- the rules above
- the approved tag catalog
- the demo external ID
- topic
- date/time
- raw address and ZIP code
- raw route text, when available
- current tags, when already present

For now, copy that generated markdown into Gemini Gem manually. Then copy the returned JSON back into your review workflow and either:

- select the approved tags directly in the UI, or
- store a proposed concept for later mapping/review.

## Batch export from local

For the remaining untagged demos, generate a copy-paste batch Markdown file:

```bash
docker compose exec -T backend python -m backend.tags_gem_export --untagged --limit 50 --output /tmp/demo-tags-gem.md --skip-migrations
```

For one or more specific demos:

```bash
docker compose exec -T backend python -m backend.tags_gem_export --external-id abc123 --external-id def456 --output /tmp/demo-tags-gem.md --skip-migrations
```

The export is read-only. It does not write tags, does not assign `Other`, and does not touch geocoding/routing data.

## Import reviewed Gemini JSON

Save the JSON portion of Gemini's response to a file, for example `gem-tags-result.json`.

Preview first:

```bash
docker compose exec -T backend python -m backend.tags_gem_import /code/gem-tags-result.json --dry-run --skip-migrations
```

Apply after the preview looks right:

```bash
docker compose exec -T backend python -m backend.tags_gem_import /code/gem-tags-result.json --apply --skip-migrations
```

Import safety rules:

- Only approved active tag slugs become final demo tags.
- Maximum two final tags are kept per demo.
- `other` is rejected by default.
- Unknown tags and proposals become review proposals, not final public tags.
- Missing demo IDs are skipped and reported.
- The importer does not change geocoding, route geometry, scraper state, or support resolutions.

If you intentionally reviewed and approved `Other`, pass `--allow-other`:

```bash
docker compose exec -T backend python -m backend.tags_gem_import /code/gem-tags-result.json --apply --allow-other --skip-migrations
```

## Batch output

For multiple demos, return:

```json
{
  "items": [
    {
      "external_id": "abc123",
      "tags": ["environment"],
      "confidence": 0.92,
      "reason": "Topic mentions Klimastreik.",
      "needs_review": false,
      "proposals": []
    }
  ]
}
```

## Safety and privacy

- Do not include secrets, session tokens, passwords, or raw IP addresses in output.
- Do not quote long police source text. Summarize only the classification reason.
- If a demo concerns sensitive groups, classify neutrally and avoid editorial language.
- If the model is unsure, prefer `needs_review: true` over guessing.
