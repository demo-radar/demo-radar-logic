# Daily briefings

DemoLogic generates one German draft from a saved day’s public event snapshot.
Demo Radar translates it with DeepL, saves both languages and handles staff
approval. Reading a published briefing does not call a model or DeepL. The daily
snapshot covers the selected day, independently of the map’s viewport and topic filters.

## Product and provider boundary

The product contract is `daily-summary-v1`, independent of the provider’s name.
The current adapter uses Hetzner. Demo Radar reads the authenticated contract and
configuration fingerprint from DemoLogic instead of maintaining another catalog.

- [Product instructions](../../configs/summary/daily-summary-v1.json)
- [Worked example sent with the prompt](../../configs/summary/examples/news-brief-v1.json)
- [Provider settings](../../configs/summary/providers/hetzner.json)

The example and actual snapshot are separate messages. Example identifiers cannot
be used as real supporting events. Version and fingerprint changes identify a
different request contract; old experiment configurations remain historical inputs.

## Editorial behavior

The reader sees a short introduction, a landscape of themes expressed through
slogans, other topics and an always-expanded event in focus. A verified daily total
counts distinct registered events in the snapshot, not every gathering in Berlin.
Broad theme counts are not presented as counts for a narrower political demand.

The visible summary stays below 200 words per language, excluding Getting around.
It does not repeat the date at the start of every paragraph. The model must avoid
unsupported motives, invented event details and claims that a selected event is
objectively the largest or most important. Staff can inspect the source records;
public source-control widgets and a second timetable are not part of the story.

Getting around uses recorded route and time facts. It cannot establish a closure,
disruption size or city-wide risk from a slogan. An official closure feed is not
connected. Missing route data does not prove travel will be unaffected.

## Queue, translation and recovery

Demo Radar owns startup/hourly checks, date selection, retry timing and the
publication state. Generation and translation have separate attempt counts:
retrying DeepL must not regenerate an already saved German draft. Reading the
same content reuses the saved result. Local/staging generation remains manual.

Tagging and summary generation share the execution lock and DemoLogic admission
gate. A provider timeout with an unknown outcome pauses new inference. Saved-answer
lookup does not call the model. Recovery retains history and missing usage.
See the [API recovery guide](../service-api.md#what-happens-if-the-connection-drops).

Drafts and revisions remain private until staff approves publication. A change in
source/configuration can justify a new draft without discarding the earlier run.
No summary-generation action changes an event’s approved topic tags.

The detailed writing/recovery iteration log is maintained in the issue tracker.
The versioned prompt and worked example preserve the actual generation behavior.
