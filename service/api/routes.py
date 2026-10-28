"""Thin HTTP routes: authenticate, delegate to the service, return JSON.

No SQL or provider-specific decisions belong here. Staff authorization is a
separate Demo Radar concern; this API authenticates the backend service token.
"""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from service.contracts import TagRequest, TagResponse
from service.gems.contracts import GemPreview, GemRequest, GemResponse
from service.inference.contracts import (
    ProfileCatalog,
)
from service.inference.coordinator import InferenceService
from service.inference.recovery import RecoveryService
from service.persistence.journal import AdmissionError
from service.summary.contracts import SummaryProfileContract, SummaryRequest, SummaryResponse

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def get_service(request: Request) -> InferenceService:
    """Resolve the startup-owned service from an incoming HTTP request."""
    return request.app.state.service


Service = Annotated[InferenceService, Depends(get_service)]


async def authenticated(
    service: Service, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    """Verify a bearer token without returning or logging supplied credentials."""
    if credentials is None or not hmac.compare_digest(
        credentials.credentials.encode("utf-8"), service.settings.token.encode("utf-8")
    ):
        raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})


auth = [Depends(authenticated)]


@router.get("/health/live")
async def live():
    """Return process liveness; this public check never calls a provider."""
    return {"status": "alive"}


@router.get("/health/ready", dependencies=auth)
async def ready(service: Service):
    """Return 200 when admission is ready, or 503 during drain/unresolved work."""
    state = service.journal.maintenance()
    available = not state["maintenance"] and not state["unresolved_attempts"]
    return JSONResponse(
        status_code=200 if available else 503,
        content={
            "ready": available,
            **state,
            "mode": service.settings.mode,
            "config_version": service.config.version,
            "summary_config_version": service.settings.summary_config_id
            if service.settings.summary_enabled
            else None,
        },
    )


@router.post("/v1/maintenance", dependencies=auth)
async def drain(service: Service):
    """Block new attempts; return 202 while admitted work is still unresolved."""
    state = service.journal.maintenance(True)
    return JSONResponse(status_code=200 if state["drained"] else 202, content=state)


@router.delete("/v1/maintenance", dependencies=auth)
async def resume(service: Service):
    """Resume only when there are no active or uncertain provider attempts."""
    return service.journal.maintenance(False)


@router.get("/v1/attempts/{request_id}", dependencies=auth)
async def attempt_status(request_id: str, service: Service):
    """Read an attempt by ID, without inference: saved result or unresolved marker.

    Returns 404 for unknown IDs, 202 for a started marker, or 200 for a saved
    success/failure. A started marker does not prove the remote call still runs.
    """
    saved = service.journal.get_attempt(request_id)
    if saved is None:
        raise HTTPException(404)
    result, status = saved
    return JSONResponse(status_code=status, content=result)


class CloseUnknownBody(BaseModel):
    """Backend-supplied operator and reason, with explicit uncertainty acceptance."""

    model_config = ConfigDict(extra="forbid")
    operator: str = Field(min_length=1, max_length=160, pattern=r".*\S.*")
    reason: str = Field(min_length=10, max_length=1000, pattern=r".*\S.*")
    accept_unknown_outcome: StrictBool

    @field_validator("operator", "reason", mode="before")
    @classmethod
    def trimmed(cls, value):
        """Check the actual text length after removing surrounding spaces."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("accept_unknown_outcome")
    @classmethod
    def acknowledged(cls, value):
        """Require the actual boolean true; strings and numbers are not consent."""
        if not value:
            raise ValueError("Accept the unknown outcome before closing it")
        return value


@router.get("/v1/recovery", dependencies=auth)
async def recovery_status(service: Service):
    """Read the shared blocker; no provider call or recovery is performed."""
    return service.journal.recovery_status()


@router.post("/v1/attempts/{request_id}/close", dependencies=auth)
async def close_unknown(request_id: str, body: CloseUnknownBody, service: Service):
    """Audit an explicit abandonment and resume unrelated work when safe."""
    return RecoveryService(service.journal).close(
        request_id, operator=body.operator, reason=body.reason
    )


@router.get("/v1/openapi.json", dependencies=auth)
async def schema(request: Request):
    """Return the generated API contract to an authenticated integration client."""
    return request.app.openapi()


@router.post("/v1/tag-suggestions", dependencies=auth, response_model=TagResponse)
async def suggest(request: TagRequest, service: Service, http_request: Request):
    """Return one suggestion or replay; rejected/busy work is never queued here."""
    replay = service.replay(request)
    selected = (
        service
        if replay is not None
        else http_request.app.state.profiles.resolve("tagging", request)
    )
    result, status = replay if replay is not None else await selected.suggest(request)
    headers = service.journal.retry_headers() if status == 429 else {}
    return JSONResponse(status_code=status, content=result, headers=headers)


@router.get(
    "/v1/task-profiles",
    dependencies=auth,
    response_model=ProfileCatalog,
    response_model_exclude_unset=True,
)
async def task_profiles(http_request: Request):
    """List executable approved profiles; no inference or default updates."""
    return http_request.app.state.profiles.catalog()


@router.get("/v1/attempts/{request_id}/execution", dependencies=auth)
async def execution_context(request_id: str, service: Service):
    """Read private saved context and timings, including retired profiles."""
    context = service.journal.execution(request_id)
    if context is None:
        raise HTTPException(404, detail="Execution context unavailable for this attempt")
    return context


@router.get(
    "/v1/daily-summary-contract",
    dependencies=auth,
    response_model=SummaryProfileContract,
    response_model_exclude_unset=True,
)
async def summary_contract(http_request: Request, config_id: str | None = None):
    """Read the active contract, or an old contract for saved-result validation.

    Demo Radar persists this response with its job. It does not maintain a
    second catalog of model names or prompt fingerprints.
    """
    from service.summary.config import SummaryConfig

    settings = http_request.app.state.service.settings
    try:
        config = SummaryConfig(settings.root, config_id or settings.summary_config_id)
    except (KeyError, ValueError):
        raise HTTPException(404, detail="Unknown summary configuration") from None
    return {**config.contract(), "max_attempts": settings.summary_max_attempts}


@router.post("/v1/daily-summary-drafts", dependencies=auth, response_model=SummaryResponse)
async def summary_draft(request: SummaryRequest, http_request: Request):
    """Generate or replay a private daily draft; never publish it here."""
    service = http_request.app.state.summary
    if service is None:
        raise AdmissionError("summary_disabled", 503)
    replay = service.replay(request)
    selected = (
        service
        if replay is not None
        else http_request.app.state.profiles.resolve("daily-summary", request)
    )
    result, status = replay if replay is not None else await selected.suggest(request)
    headers = service.journal.retry_headers() if status == 429 else {}
    return JSONResponse(status_code=status, content=result, headers=headers)


class SpendingEvidence(BaseModel):
    """Operator evidence of actual USD charges, separate from recovery of an answer."""

    model_config = ConfigDict(extra="forbid", strict=True)
    amount_usd: str = Field(min_length=1, max_length=30)
    operator: str = Field(min_length=1, max_length=160, pattern=r".*\S.*")
    reason: str = Field(min_length=10, max_length=1000, pattern=r".*\S.*")
    verified_account_evidence: StrictBool

    @field_validator("operator", "reason", mode="before")
    @classmethod
    def trimmed(cls, value):
        return value.strip() if isinstance(value, str) else value


@router.get("/v1/attempts/{request_id}/spending", dependencies=auth)
async def spending_evidence(request_id: str, service: Service):
    """Read the reservation and reconciliation; never contact the provider."""
    from service.persistence.spending import inspect

    with service.journal.connection() as db:
        return inspect(db, request_id)


@router.post("/v1/attempts/{request_id}/spending", dependencies=auth)
async def reconcile_spending(request_id: str, body: SpendingEvidence, service: Service):
    """Audit verified charges after local execution and unknown-answer recovery."""
    from service.persistence.locking import activity_lock
    from service.persistence.spending import settle

    if not body.verified_account_evidence:
        raise AdmissionError("invalid_request", 422)
    with activity_lock(service.journal.path, exclusive=True), service.journal.connection() as db:
        return settle(db, request_id, body.amount_usd, body.operator.strip(), body.reason.strip())


@router.get("/v1/gem-profiles", dependencies=auth, response_model=ProfileCatalog)
async def gem_profiles(http_request: Request):
    """Read executable Gem identities without inference."""
    return http_request.app.state.gems.catalog()


@router.post("/v1/gems/tagging/preview", dependencies=auth)
async def gem_preview(body: GemPreview, http_request: Request):
    """Return the same system/context messages for copying and API execution."""
    base = http_request.app.state.profiles.services.get(("tagging", body.profile_id))
    if base is None or base.config.sha256 != body.profile_sha256:
        raise AdmissionError("unsupported_configuration", 422)
    service = http_request.app.state.gems_by_base[base.config.version]
    return {
        "schema_version": 1,
        "profile": http_request.app.state.gems.describe(service),
        "gem_version": service.config.gem.version,
        "gem_sha256": service.config.gem_sha256,
        "messages": service.config.payload(body.context)["messages"],
    }


@router.post("/v1/gems/tagging", dependencies=auth, response_model=GemResponse)
async def run_tagging_gem(body: GemRequest, http_request: Request):
    """Run one pinned Gem; saving the JSON does not publish tags."""
    root = http_request.app.state.service
    replay = root.replay(body)
    selected = root if replay is not None else http_request.app.state.gems.resolve("tagging", body)
    result, status = replay if replay is not None else await selected.suggest(body)
    return JSONResponse(
        content=result,
        status_code=status,
        headers=root.journal.retry_headers() if status == 429 else {},
    )
