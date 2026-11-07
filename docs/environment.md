# Service environment settings

DemoLogic owns provider credentials, approved profiles and execution admission.
Radar owns client timeouts, scheduling, saved defaults and review. Similar names
in their separate environments are not interchangeable. The root `.env` is for
notebooks; this service never loads it.

## Loading

Compose reads `service/.env` only when selected with `--env-file service/.env`.
Shell values override that file; `compose.yml` forwards only its listed service
variables. Python reads its process environment. No private file is read by the
settings loader. `compose.images.yml` changes the image/build source only, using
the same environment forwarding for staging and production.

Booleans accept `true`/`false`, ignoring case and surrounding whitespace. Empty
or unrecognised values fail explicitly. Numeric settings must be finite and
within their existing bounds. Errors name the variable without echoing its value.
Standardise old noncanonical flag spellings before the combined release; do not
change provider activation or spending limits as part of syntax cleanup.

Settings are Pydantic-validated frozen dataclasses, using the existing dependency.
Field constraints own types, bounds and allowed values; the cross-field live-account
guard remains explicit. Factories/tests still use `dataclasses.replace()` and
`asdict()`, preserving numeric representations and saved-request construction.
Credentials are excluded from repr, and supplied inputs are hidden in validation
error text. Do not log full dataclass dictionaries.

## Variable reference

These are application defaults, not instructions to replace current settings.
The complete fresh-install template is `service/.env.example`.

| Variable | Default | Purpose / limits |
| --- | --- | --- |
| `DEMOLOGIC_SERVICE_TOKEN` | empty | Secret shared with Radar; required for startup. |
| `DEMOLOGIC_DATABASE` | `data/service/inference.sqlite` | Direct-process journal path. Compose fixes `/app/data/service/inference.sqlite` inside the persistent volume. A host override is deliberately not forwarded. |
| `DEMOLOGIC_MODE` | `demo` | `demo` or `live`. Demo uses synthetic adapters. |
| `DEMOLOGIC_CONFIG_ID` | `qwen-v4-v1` | Approved initial tagging profile; not an arbitrary model/endpoint. |
| `HETZNER_API_KEY` | empty | Secret provider key. Live Hetzner needs this and free-account confirmation. |
| `DEMOLOGIC_FREE_TIER_CONFIRMED` | `false` | Operator confirms the free account; checked again at dispatch. |
| `DEMOLOGIC_TIMEOUT_SECONDS` | `60` | Provider timeout, 1–60 seconds; separate from Radar's client wait. |
| `DEMOLOGIC_MIN_INTERVAL_SECONDS` | `1` | Shared pacing, 0–300 seconds. |
| `DEMOLOGIC_MAX_ATTEMPTS_PER_EVENT` | `3` | 1–10 server attempts per event; never resets Radar's job or shared attempt ceilings. |
| `DEMOLOGIC_SUMMARY_ENABLED` | `false` | Register summary execution services. Does not schedule jobs. |
| `DEMOLOGIC_SUMMARY_CONFIG_ID` | `hetzner-daily-v1` | Approved initial summary profile. |
| `DEMOLOGIC_SUMMARY_MAX_ATTEMPTS` | `3` | Either 3 or 5 attempts per summary input. |
| `DEMOLOGIC_SUMMARY_TIMEOUT_SECONDS` | `60` | Provider timeout, 1–60 seconds. |
| `DEMOLOGIC_RETAINED_TAG_CONFIGS` | empty | Comma-separated approved profiles needed by persisted work. |
| `DEMOLOGIC_RETAINED_SUMMARY_CONFIGS` | empty | Comma-separated approved summary profiles needed by persisted work. |
| `DEMOLOGIC_ENVIRONMENT` | `unspecified` | `local`, `staging`, `production`, `test`, or `unspecified`; measurement label, not a scheduling switch. Example uses `local`. |
| `GEMINI_API_KEY` | empty | Secret Gemini key; no OpenAI adapter is configured by adding a key here. |
| `DEMOLOGIC_GEMINI_ENABLED` | `false` | Allow approved Gemini profiles, subject to all monetary guards. |
| `DEMOLOGIC_GEMINI_ACCOUNT` | empty | Non-secret billing-account label; one persistent journal per account. |
| `DEMOLOGIC_PAID_RUN_USD` | empty | Approved ceiling per logical run. |
| `DEMOLOGIC_PAID_PERIOD_USD` | empty | Shared UTC-day ceiling. |
| `DEMOLOGIC_PAID_ACCOUNT_USD` | empty | Account UTC-day ceiling. |
| `DEMOLOGIC_IMAGE` | `demologic:local` | Compose-only image selection. Image deployment override requires an approved digest. |

Paid limits remain exact USD strings, not floats. Missing credentials, approved
pricing or positive monetary limits leave paid execution unavailable; startup
alone does not establish availability. See [provider settings and spending](provider-settings.md)
for admission, reservations and reconciliation. No budgets are invented here.
Models, endpoints and prices belong in reviewed catalog assets, not new environment
variables. A flag cannot override those assets or bypass an unknown outcome.

Staging's existing override caps server tagging attempts at one and summary
attempts at three. Logic has no scheduler: Radar must keep local/staging manual.
For upgrades/rollback, preserve the journal and profiles required by saved work;
follow the [task execution guide](task-execution.md#keep-older-profiles).
