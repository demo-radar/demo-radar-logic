"""Stable request identity, including compatibility with saved legacy attempts."""

from service.inference.results import fingerprint


def request_data(request):
    """Omit the new optional field when an older caller did not supply it."""
    return request.model_dump(exclude={"execution"} if request.execution is None else set())


def request_identity(request, config_sha256, mode, task):
    """Keep legacy fingerprints byte-compatible while pinning new request context."""
    value = {"request": request_data(request), "config": config_sha256, "mode": mode}
    if task == "daily-summary":
        value["task"] = task
    return fingerprint(value)


def source_identity(request, task):
    """Identify an input independently of its model, prompt or retry request ID."""
    if task == "daily-summary":
        return request.snapshot_sha256
    return fingerprint(
        {"event": request.event.model_dump(), "source_version": request.source_version}
    )
