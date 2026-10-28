"""Safe error explanations shared by HTTP admission and completed attempts.

api/exception_handlers.py returns ``{"error": detail}`` before inference; inference/results.py embeds
the same detail in a saved attempt response after a provider failure. The future
Demo Radar worker stores this object and its staff UI displays ``error.message``
as text. This module does not render a screen or send notifications.

Clients can branch on ``code`` and show ``message`` to a person. Messages are
locally defined: database details, provider text, titles and keys never appear.
"""

from http import HTTPStatus

from service.contracts import ErrorDetail
from service.gems.errors import GEM_ERRORS
from service.summary.errors import SUMMARY_ERRORS

MESSAGES = {
    **GEM_ERRORS,
    **SUMMARY_ERRORS,
    "token_count_unavailable": "Provider input size could not be checked. No generation was admitted; try again later.",
    "spending_review_required": "Reported usage exceeded its reservation. An operator must reconcile spending before more paid work.",
    "provider_disabled": "This provider is disabled. An operator must approve activation.",
    "spending_not_configured": "Paid execution requires approved run, daily and account limits.",
    "pricing_review_required": "The provider pricing needs an operator review before another call.",
    "spending_limit": "The shared spending allowance cannot cover another call. No inference was admitted.",
    "job_configuration_mismatch": "This job already uses a different execution profile. Keep its original settings.",
    "unsupported_task_profile": "This task/profile combination is unavailable. Keep the saved job and check compatible service versions.",
    "recovery_inflight": "A local inference call is still running. Wait for it to finish before recovery.",
    "recovery_wait_required": "Wait until 15 minutes after the saved timeout before closing it.",
    "attempt_not_finalized_unknown": "Only a finalized unknown answer can be closed here. An unfinished request needs investigation.",
    "resolution_conflict": "This attempt already has a different recovery decision. Read its saved result.",
    "maintenance_required": "Pause admission before recovering an unknown attempt.",
    "event_outcome_closed_unknown": "An operator closed an unknown result for this input. It cannot be sent again; review it manually.",
    "invalid_request": "Check the request fields against the API contract.",
    "unauthorized": "A valid service bearer token is required.",
    "not_found": "The requested route or attempt does not exist.",
    "unsupported_configuration": "This service does not have the requested model configuration enabled.",
    "synthetic_event_required": "Demo mode accepts only event IDs beginning with synthetic-.",
    "journal_unavailable_recovery_required": "The attempt could not be safely read or saved. Stop and inspect the journal before retrying.",
    "idempotency_conflict": "This request ID was already used with different input. Use its original input to retrieve the result.",
    "attempt_already_finalized": "This attempt cannot be completed again. Its saved result has been preserved.",
    "attempt_unresolved": "This attempt has no confirmed saved outcome. Check its status before retrying.",
    "maintenance": "New inference is paused for maintenance.",
    "inference_busy_or_recovery_required": "An attempt is active or its outcome is uncertain. New work is blocked.",
    "provider_pacing": "Wait for the provider cooldown before submitting another attempt.",
    "event_already_completed_use_original_request": "This event input already has a result. Retrieve it using the original request ID.",
    "event_attempt_limit": "This event has reached the operator-configured attempt limit.",
    "batch_limit": "This job has reached its event or total-attempt limit.",
    "invalid_provider_response": "The model response does not match the required output or metadata format.",
    "invalid_provider_json": "The provider response could not be safely decoded. Its outcome requires review.",
    "provider_response_too_large": "The provider response exceeded the size limit. Its outcome requires review.",
    "provider_quota_exhausted": "The provider reported exhausted credit or quota. Stop and check the account.",
    "provider_outcome_unknown": "The provider did not return a confirmed result before the connection or deadline failed. Check before retrying.",
}


def error_detail(code, status, retry_after=0, fields=None):
    """Build an ErrorDetail dictionary from a local code and public HTTP status.

    Args:
        code: Stable internal code, such as ``maintenance``; never provider text.
        status: Public HTTP status sent to the API caller.
        retry_after: Remaining cooldown in seconds, if applicable.
        fields: Invalid request field paths, without submitted values.
    Returns:
        A JSON-ready dictionary containing the public message and error metadata.
        Callers put it under ``error``; a UI can then display ``error.message``.

    Example:
        ``error_detail("maintenance", 503)["message"]`` returns
        ``"New inference is paused for maintenance."``.

    Retryable means a later deliberate attempt may be appropriate; it never
    authorizes automatic retry, bypassing limits, or clearing an unknown outcome.
    """
    message = MESSAGES.get(code)
    if message is None and code.startswith("provider_http_"):
        number = code.removeprefix("provider_http_")
        message = (
            f"The provider returned HTTP {number}. Check its availability, credentials or limits."
        )
    return ErrorDetail(
        code=code,
        message=message or HTTPStatus(status).phrase,
        http_status=status,
        retry_after_seconds=retry_after,
        retryable=code in {"provider_http_429", "provider_pacing"},
        fields=fields,
    ).model_dump()
