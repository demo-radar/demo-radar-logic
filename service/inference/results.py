"""Build response values independently of HTTP routing and provider execution.

The public schema lives in service/contracts.py. This module maps a completed attempt
into that schema, retaining provider usage and stable reproduction fingerprints.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi.responses import JSONResponse

from service.contracts import TagResponse
from service.errors import error_detail


def fingerprint(value):
    """Hash canonical public inputs for idempotency, without storing title text."""
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def utc_now():
    """Return an explicit UTC timestamp; durations use the monotonic clock."""
    return datetime.now(UTC).isoformat()


def usage_counts(usage):
    """Normalize known token counts while retaining raw provider category meaning.

    Unknown values stay null. Cached-input and reasoning counts are subsets of
    input/output, so consumers must not add them to the total a second time.
    """
    usage = usage if isinstance(usage, dict) else {}

    def count(value):
        return value if type(value) is int and value >= 0 else None

    prompt_details = usage.get("prompt_tokens_details")
    completion_details = usage.get("completion_tokens_details")
    prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
    completion_details = completion_details if isinstance(completion_details, dict) else {}
    return {
        "input_tokens": count(usage.get("prompt_tokens")),
        "output_tokens": count(usage.get("completion_tokens")),
        "total_tokens": count(usage.get("total_tokens")),
        "cached_input_tokens": count(prompt_details.get("cached_tokens")),
        "reasoning_tokens": count(completion_details.get("reasoning_tokens")),
        "token_semantics": "cached input and reasoning are subsets; retain usage_raw",
    }


@dataclass
class AttemptOutcome:
    """Internal result of one provider attempt, including known failure evidence.

    Args:
        tags: Suggested tags on success; an empty list means abstention.
        metadata: Provider model, request ID and usage, never the generated text.
        state: ok, failed, or unknown (remote completion cannot be confirmed).
        code: Stable public error code; null on success.
        http_status: HTTP response status, separate from the provider status.
        retry_after: Provider cooldown in seconds. This does not initiate a retry.
    """

    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    state: str = "ok"
    code: str | None = None
    http_status: int = 200
    retry_after: float = 0


def build_result(request, config, runtime, outcome, started, wall_start, attempt_number):
    """Construct and validate the saved API response for one admitted attempt.

    Args:
        request: Validated TagRequest; identifiers are not sent to the provider.
        config: Loaded, fingerprinted inference configuration.
        runtime: Service settings (including demo/live mode).
        outcome: AttemptOutcome returned by the coordinator.
        started: Monotonic start time used to measure elapsed seconds.
        wall_start: UTC ISO timestamp for the audit trail.
        attempt_number: Persisted attempt count for this event input.

    Returns:
        A JSON-safe dictionary matching TagResponse, ready for durable storage.
        Validation errors propagate before success can be saved.
    """
    body, tags = outcome.metadata, outcome.tags
    state, code = outcome.state, outcome.code
    payload = config.payload(request.event.title)
    result = {
        "request_id": request.request_id,
        "job_id": request.job_id,
        "event_id": request.event.id,
        "source_version": request.source_version,
        "config_version": config.version,
        "config_sha256": config.sha256,
        "input_sha256": fingerprint(
            {"event": request.event.model_dump(), "source_version": request.source_version}
        ),
        "payload_sha256": fingerprint(payload),
        "rubric_sha256": config.rubric_sha256,
        "taxonomy_version": "v2",
        "mode": runtime.mode,
        "tags": tags if state == "ok" else None,
        "status": ("suggested" if tags else "abstained") if state == "ok" else state,
        "requires_staff_review": True,
        "error": error_detail(code, outcome.http_status, outcome.retry_after) if code else None,
        "replayed": False,
        "new_provider_calls": int(runtime.mode == "live"),
        "statistics": {
            "schema_version": 1,
            "attempt_id": request.request_id,
            "attempt_number": attempt_number,
            "provider": config.provider if runtime.mode == "live" else "synthetic",
            "requested_model": config.model,
            "returned_model": body.get("model"),
            "provider_request_id": body.get("id"),
            "started_at": wall_start,
            "finished_at": utc_now(),
            "duration_seconds": time.monotonic() - started,
            "provider_call_occurred": runtime.mode == "live",
            "outcome": state,
            "usage_raw": body.get("usage"),
            **usage_counts(body.get("usage")),
        },
    }
    # JSONResponse bypasses FastAPI response validation. Validate and render
    # before committing success so every saved answer can actually be replayed.
    result = TagResponse.model_validate(result, strict=True).model_dump(mode="json")
    JSONResponse(content=result)
    return result
