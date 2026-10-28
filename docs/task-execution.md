# How tasks run

DemoLogic handles tagging and daily summaries. A **profile** fixes the provider,
model, instructions and output format. Its ID and hash identify the exact version.

Demo Radar chooses jobs and handles permissions, review and publication. DemoLogic
checks profiles, calls the provider and saves results. Route execution remains
disabled. Radar stores independent tagging and summary defaults with an audit trail.
See [provider setup and spending](provider-settings.md) for activation requirements.

## The flow

```mermaid
flowchart LR
    Radar[Radar sends a job] --> Saved{Answer already saved?}
    Saved -->|yes| Read[Return the original answer]
    Saved -->|no| Check[Check profile and shared limits]
    Check --> Record[Save attempt settings and reserve paid cost]
    Record --> Model[Call the provider once]
    Model --> Save[Validate and save the result]
    Read --> Review[Review in Radar]
    Save --> Review
```

Tags and summaries share one execution lane. Only one call runs at a time.
Duplicate requests return the saved answer without another call. Jobs keep their
original settings; changing profiles does not reset classifier or summary retry limits.

**An unknown outcome blocks new calls, including after a restart or profile
change.** Use the [recovery procedure](service-api.md#what-happens-if-the-connection-drops)
before continuing. Saved suggestions still need review before publication.

## Inspect the service

The [API reference](service-api.md#authentication-and-endpoints) lists the
authenticated profile catalog and attempt lookup endpoints. These inspection
endpoints make no model calls or settings changes. The optional request fields
are documented in the [tagging contract](service-api.md#tagging-contract).

An `enabled` profile has configured execution requirements; it does not prove
that a live call succeeded or that spending allowance remains.
Summary profiles appear only when summaries are enabled.

## Run a Gem through Radar

Radar offers **Copy Gem** and admin-only **Send to DemoLogic**. Both use the same
versioned `configs/gems/tagging-v1.json` instructions and explicit demonstration
context. Instructions become the system prompt; source facts become the user
context. No saved chat history, attachments or hidden Gem configuration is inferred.

`POST /v1/gems/tagging/preview` returns these messages and the pinned Gem profile
without inference or a spending reservation. `GET /v1/gem-profiles` lists available
Gem profiles. `POST /v1/gems/tagging` admits one request through the shared controller,
spending guards and journal. Lookup/recovery use the existing attempt endpoints.

A manual Gem send is a new explicit execution, including for an already-tagged
or previously processed demo. Radar authorizes it and supplies a fresh `job_id`
and `request_id`. That job admits at most **one** provider attempt: a duplicate
request replays its saved outcome, and another request ID in the same job cannot
retry generation. Previous classifier/Gem outcomes do not exhaust a new manual
execution. There is no automatic Gem retry or batch cooldown; shared provider
pacing, sequential admission, maintenance and spending ceilings still apply.
The `execution` object is required, with `task: tagging`, `origin: manual_api`
and the exact Gem `profile_sha256`; scheduled Gem calls are rejected.

An unresolved Gem still blocks all new inference. After explicit audited closure,
a new manual execution may revisit the demo; the old unknown answer and its
reserved spending remain intact. Classifier and summary source retry limits are
unchanged. Changing request/job IDs is never an automatic recovery mechanism.

The saved `gem_reply` contains the event ID, tags, self-reported confidence and
explanation. It is private and requires review. The Gem is separate from the
research title-only tagging profile; that profile's prompt and output stay unchanged.
Version the Gem definition when changing its instructions/schema, and keep Radar's
pinned copy in sync. Mismatched fingerprints or messages block sending.

## Keep older profiles

Outstanding jobs may need a previous profile after an upgrade. Keep its approved
assets and add its ID to the appropriate comma-separated startup setting:

* `DEMOLOGIC_RETAINED_TAG_CONFIGS`
* `DEMOLOGIC_RETAINED_SUMMARY_CONFIGS`

Gemini profiles are included automatically; the summary profile requires summaries
to be enabled. Empty retention settings add no other profiles. Retention does not
change Radar's defaults.
Summary retention requires summaries enabled. Unknown or altered assets stop startup.

Removing a profile stops new work using it. Saved answers remain available through
attempt lookup; identical requests can also replay while that task is enabled.
Restore compatible versions for unfinished work instead of replacing its settings.

## Upgrade and rollback

| Versions | Behaviour |
| --- | --- |
| Old Radar, new Logic | Existing requests remain compatible. |
| New Radar, old Logic | A missing catalog (404/405) uses the existing pinned readiness check. Other catalog errors stop work. |
| Both new | Radar checks the exact profile ID and hash, including retained profiles. |
| Older Logic after rollback | Older service versions cannot read the updated request database (schema 3). Restore a service version that supports it and keep the current database intact. |

For an upgrade:

1. Pause new jobs, finish active calls and resolve unknown outcomes.
2. Back up the private journal and required profile assets.
3. Test with synthetic inputs and retain profiles needed by saved jobs.
4. Upgrade Logic and restart both the Radar API and its separate worker with
   matching code; check catalog/readiness before resuming Radar.

For rollback, pause and drain again, preserve the current journal, and restore
a compatible service image with its approved profile files. Keep the current request
database: it records saved answers, unresolved calls and money already reserved.
Use a service version that understands those records. Do not delete the database,
change providers to bypass an unresolved call, or restore an old backup over newer records.

## Saved history and timing

The journal adds an execution table while preserving original answers, usage and
recovery records. New attempts save their settings before execution. Older records
recover only known facts; missing context or timing stays unavailable.

Private logs record execution and outcomes. `provider_seconds` measures one adapter
call, including failures and parsing—not provider-reported inference time. Replay
adds no calls or usage. Public metric labels exclude source text, credentials and
request IDs.
