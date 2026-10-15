"""Translate HTTP, validation and journal failures into public JSON responses.

These handlers send the response. The shared service.errors module supplies
safe messages, also used in persisted provider outcomes. Raw provider bodies,
request values and credentials are never used as user-facing error messages.
"""

from fastapi.responses import JSONResponse

from service.errors import error_detail


async def invalid_input(_, exc):
    """Return invalid field paths without echoing submitted private values."""
    # Field names can also be user-supplied; escape malformed Unicode safely.
    fields = [
        [str(part).encode("utf-8", "backslashreplace").decode() for part in e["loc"]]
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": error_detail("invalid_request", 422, fields=fields),
            "inference_admitted": False,
        },
    )


async def unavailable_journal(_, exc):
    """Fail closed on database errors; an unresolved dispatch must not be retried."""
    return JSONResponse(
        status_code=503,
        content={"error": error_detail("journal_unavailable_recovery_required", 503)},
    )


async def rejected(_, exc):
    """Confirm a refused start; never make that claim about a save failure."""
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else {}
    content = {"error": error_detail(exc.code, exc.status, exc.retry_after or 0)}
    # Journal.finish can raise this after provider inference already happened.
    if exc.code != "attempt_already_finalized":
        content["inference_admitted"] = False
    return JSONResponse(
        status_code=exc.status,
        headers=headers,
        content=content,
    )


async def http_error(_, exc):
    """Use the same error shape for authentication, missing routes and HTTP errors."""
    code = {401: "unauthorized", 404: "not_found"}.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={"error": error_detail(code, exc.status_code), "inference_admitted": False},
    )
