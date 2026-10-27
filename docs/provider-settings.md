# Provider settings and spending

This feature is shipped disabled. Demo Radar chooses a default separately for
**tagging** and **daily summaries**. DemoLogic owns the approved profiles,
credentials, pricing and dispatch checks. Routes are unavailable; DeepL translation
remains separate. Copy-and-paste Gem controls are unchanged.

## Ownership and changes

The [shared task flow](task-execution.md#the-flow) explains admission, execution
and replay. Provider settings add these ownership and change rules:


Radar's PostgreSQL stores environment, settings version, old/new choices, actor
and time. An admin save includes the version they read. A stale save returns 409;
service validation or database failure leaves the old defaults intact. The screen
acknowledges both choices and explains that only new jobs change. Saved jobs
validate their original profile again at dispatch, without vendor substitution.
A manual override applies only to that run; scheduled work uses the saved default.
Support users cannot read/change settings, override providers or start API runs.
The catalog supplies the provider, exact model, profile fingerprint and availability
reason. Support shows Available or Unavailable with that reason. Available means
configured for execution; it is not a live health check or a remaining-balance check.

## Reviewed profiles

`service/providers/models.py` records each approved model, its provider and any
reviewed paid pricing. Spending checks look up the selected model; they do not
reuse another model's rates. Hetzner's registered Qwen model requires explicit
free-account confirmation. A future model needs a catalog entry, an approved task
profile, compatible transport and tests before activation. Existing versioned JSON
profiles and saved spending records retain their original identities and rates.

| Task | Hetzner | Google Gemini |
| --- | --- | --- |
| Tagging | `qwen-v4-v1` | `gemini-v4-v1` |
| Daily summary | `hetzner-daily-v1` | `gemini-daily-v1` |

The shared prompt remains `configs/summary/daily-summary-v1.json`. The older
`daily-summary-v1` ID remains readable for saved jobs. If queued work still needs
that ID, include it in `DEMOLOGIC_RETAINED_SUMMARY_CONFIGS` until the work finishes;
do not rename saved requests or rewrite their history.

The Gemini profiles use `gemini-3.8-flash`, a stable model supporting structured
text output, with low thinking and no search/tools. They reuse the v4 tagging
guide and the current summary prompt, worked example and output schema. These
are new service adapters, **not evidence of equivalent benchmark accuracy**.
Native input, visible output, thinking and cache usage are normalized; the native
usage record stays saved. Thinking is included in output, never counted twice.
Missing counts remain unknown. Invalid/truncated output is a failed saved attempt.
429 and timeout responses do not trigger adapter retries or fallback.

Reviewed 18 October 2026 against Google's [model specification](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash),
[REST contract](https://ai.google.dev/api/generate-content) and
[standard pricing](https://ai.google.dev/gemini-api/docs/pricing).
Account access and live compatibility still need an approved smoke check.

## Operator controls

Keep `DEMOLOGIC_PROVIDER_SETTINGS_ENABLED=false` in Radar's `.env_ai` until the
combined feature release is approved. For synthetic checks, enable it with Logic
in demo mode: all profiles return fixtures without contacting a provider.

Gemini live execution additionally requires the following **Logic-only** settings:

- `GEMINI_API_KEY` and `DEMOLOGIC_GEMINI_ENABLED=true`.
- `DEMOLOGIC_GEMINI_ACCOUNT`: a non-secret billing-account label.
- Approved positive USD amounts in `DEMOLOGIC_PAID_RUN_USD`,
  `DEMOLOGIC_PAID_PERIOD_USD`, and `DEMOLOGIC_PAID_ACCOUNT_USD`.

For the production release, set these values in production's private `service/.env`.
Use production-approved limits and the matching account key; do not copy local test
budgets. Enabling Gemini makes it selectable without changing the current defaults.
After the tested combined release, verify its status in Support's AI provider
settings before choosing it for tagging or summaries.

No monetary amounts are supplied by default. Missing/invalid limits, account,
credentials or expired prices refuse before provider HTTP. Insufficient allowance
refuses generation after the read-only token count.
Hetzner still requires its key and explicit free-account confirmation. Neither a
browser nor an individual request can change prices, ceilings or destinations.
Keep credentials in Logic's private `service/.env`; never send them through Radar.

**Activation checklist:** complete the provider, execution and monitoring subtasks;
pass offline integration/E2E; obtain operator approval of account, prices and limits;
then run a bounded live check as part of the combined feature release. Do not enable
one paid task early because its adapter tests passed.

## How money is counted

All values use integer millionths of USD. A logical run has one allowance across
its retries. Summary jobs with the same model input share that run ceiling even
when a provider change creates a new pinned job; changing providers cannot reset it.
An explicit selection of different demonstrations is a different input. All paid tasks and origins share a UTC-day service ceiling and an
account UTC-day ceiling. Saved limits cannot be raised within an existing allowance.
The journal's sequential lane and persisted cooldown also pace providers/accounts.

Before a new Gemini generation, make one bounded `countTokens` request using the
same prompt, system instructions and model. Google excludes output schemas from
this count, so include the serialized generation configuration as extra text for
counting only. This does not change the generation prompt. Add 1,024 input tokens
for protocol differences and reserve the configured output maximum, including
thinking: 4,096 tokens for tags and 8,192 for summaries. The count check has a
five-second timeout and no retries. If counting fails or the allowance is too
small, no generation or paid attempt is admitted. Saved answers skip counting.

Google's [token-count API](https://ai.google.dev/api/tokens) and
[counting clarification](https://discuss.ai.google.dev/t/gemini-api-counttokens/188451)
describe the counted fields and excluded schemas. Token counting generates no
answer and is unbilled. The standard prices remain $0.75 per million input tokens
and $3.75 per million output tokens through 31 December 2026. For example, 20,000
counted input tokens plus the margin and 4,096 output tokens reserve **$0.031128**.
Older saved reservations keep their original full-model bounds.

Known complete usage replaces the reservation with its calculated cost, rounded
up to a millionth of a dollar. Cached input is charged at the full input rate for
this conservative local ceiling. The provider invoice remains authoritative. A different returned model or usage
above the saved reservation bounds pauses paid execution for an audited account check.

Failure does not mean free. Missing/inconsistent usage, a crash, or an unknown
outcome keeps the reservation. Unreconciled reservations carry into the next UTC
day; confirmed charges reset out of the daily allowance at midnight. Run allowances
do not reset. Restarting, changing profiles/accounts or closing an unknown answer
cannot erase spending history. Explicit retries reserve again.

These are **single-journal controls**, not a distributed billing system. Use one
persistent journal per paid account; other apps or hosts using that account are
outside this ledger. Do not use account aliases or another journal to raise a cap.
Check provider billing limits as well. A new provider/currency or pricing change
requires a reviewed pricing revision and tests. This pricing revision refuses new
calls after 31 December 2026 rather than silently using outdated rates.

## Reconcile and roll back

Authenticated `GET /v1/attempts/{id}/spending` returns the reservation, confirmed
charge (if known), currency and pricing revision. It performs no inference.
After checking provider account evidence, an operator may POST to that same path:

```json
{
  "amount_usd": "0.000027",
  "operator": "operator-id",
  "reason": "Verified charge against the provider account record.",
  "verified_account_evidence": true
}
```

The amount is illustrative, not a budget recommendation. This records a separate
audit and leaves the original answer/usage unchanged. A started crash marker cannot
be settled here; investigate it first. An unknown answer must complete the existing
15-minute recovery procedure before monetary reconciliation. Closing that answer
alone retains the reservation. Do not assume zero without verified account evidence.

Journal schema 3 adds spending and audit tables. Back up the journal before upgrade.
Older binaries refuse this schema; roll back to a compatible image, not an older
journal backup that would discard charges or unknown work. Retain profiles needed
by queued jobs; use the [task guide](task-execution.md#keep-older-profiles).
