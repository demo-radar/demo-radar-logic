"""The API's shared forms: what a caller sends and what the service returns.

These Pydantic classes are data schemas, not database tables or model logic.
They validate JSON and generate the OpenAPI documentation. TagRequest is the
input form, TagResponse the output form, and ErrorDetail explains failures.

Example input (no real event data):
    {"request_id": "r1", "job_id": "j1", "source_version": "synthetic-v1",
     "event": {"id": "synthetic-1", "title": "Für sichere Radwege"}}

Unsupported fields return HTTP 422 before inference. Results are checked before
being saved; an invalid response must not become a replayable success.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Identifier = Annotated[
    str, StringConstraints(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")
]


class Event(BaseModel):
    """Event information supplied by Demo Radar for a single prediction.

    Attributes:
        id: Stable source identifier, used for tracing and limits, not model input.
        title: Original UTF-8 text (1–4,000 characters); not cleaned or rewritten.

    Separate date/location context is deliberately absent from this evaluated
    input variant. Dates or places already in the title remain visible.
    """

    model_config = ConfigDict(extra="forbid", strict=True)
    id: Identifier
    title: Annotated[str, StringConstraints(min_length=1, max_length=4000)]

    @field_validator("title")
    @classmethod
    def meaningful_title(cls, title):
        """Reject blank text while preserving the original title byte-for-byte."""
        if not title.strip():
            raise ValueError("Title must contain text")
        try:
            title.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Title must contain valid Unicode") from exc
        return title


class ExecutionContext(BaseModel):
    """Optional pinned context from an authenticated backend, never model settings."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    task: Literal["tagging", "daily-summary"]
    profile_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    origin: Literal["manual_api", "scheduled"]


class TagRequest(BaseModel):
    """Idempotent request from the future background worker.

    Attributes:
        request_id: Unique attempt ID. Repeat identical input to replay its answer.
        job_id: Caller-owned batch ID; groups at most 40 distinct events.
        model_id: Approved config name, not an arbitrary provider model string.
        taxonomy_version: v2 defines the allowed topic slugs.
        source_version: Stable source snapshot/revision used for duplicate detection.
        input_variant: F0 means original title with the pinned rubric.
        event: Event ID and original title.

    A deliberate retry needs a new request_id but shares the event's persisted
    attempt allowance (three by default). Clients cannot override that allowance.
    Extra search, threshold or context fields fail validation with HTTP 422.
    """

    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: Identifier
    job_id: Identifier
    model_id: Identifier = Field(
        default="qwen-v4-v1",
        description="Approved configuration ID, checked against the running service.",
    )
    taxonomy_version: Literal["v2"] = "v2"
    source_version: Identifier
    input_variant: Literal["F0"] = "F0"
    event: Event
    execution: ExecutionContext | None = None


class AttemptStatistics(BaseModel):
    """Measurements of the original attempt, unchanged when a result is replayed.

    Identity fields link the attempt to its provider/model. UTC timestamps are
    for audit; duration_seconds uses a monotonic clock. outcome distinguishes a
    valid completion, a known failure and an uncertain remote outcome.

    usage_raw retains the provider's counters. Normalized input/output/total
    counts are null when absent, not zero. Cached input and reasoning tokens
    are subsets; adding them again would overcount. provider_call_occurred says
    a live attempt was made, not that the provider billed it.
    """

    schema_version: Literal[1]
    attempt_id: str
    attempt_number: int
    provider: str
    requested_model: str
    returned_model: str | None
    provider_request_id: str | None
    started_at: str
    finished_at: str
    duration_seconds: float
    provider_call_occurred: bool
    outcome: Literal["ok", "failed", "unknown"]
    usage_raw: dict | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cached_input_tokens: int | None
    reasoning_tokens: int | None
    token_semantics: str


class ErrorDetail(BaseModel):
    """Machine-readable error code plus a safe explanation for people.

    Attributes:
        code: Stable name for client logic, for example provider_pacing.
        message: Local explanation; never raw provider/SQL text or a credential.
        http_status: Status used for the original attempt/admission response.
        retryable: A later deliberate retry may help, subject to every limit.
        retry_after_seconds: Original provider delay (the HTTP header on replay
            shows the remaining wait instead).
        fields: Invalid input field paths, if this was a validation error.
    """

    code: str
    message: str
    http_status: int
    retryable: bool = False
    retry_after_seconds: float = 0
    fields: list[list[str]] | None = None


class TagResponse(BaseModel):
    """Saved answer returned to the worker, not an approval to change event tags.

    tags is a list on success (empty for abstention), but null for a failure.
    status explains which happened. error contains ErrorDetail on failure.
    Identity/version/fingerprint fields allow reproduction without storing titles.
    requires_staff_review is always true for a new model suggestion.

    replayed=true means this is a saved answer. new_provider_calls=0 prevents
    callers counting the original statistics again. Synthetic mode also makes
    zero provider calls. No calibrated confidence is claimed by this schema.
    """

    request_id: str
    job_id: str
    event_id: str
    source_version: str
    config_version: str
    config_sha256: str
    input_sha256: str
    payload_sha256: str
    rubric_sha256: str
    taxonomy_version: Literal["v2"]
    mode: Literal["demo", "live"]
    tags: list[str] | None
    status: Literal["suggested", "abstained", "failed", "unknown"]
    requires_staff_review: Literal[True]
    error: ErrorDetail | None
    replayed: bool
    new_provider_calls: int
    statistics: AttemptStatistics
