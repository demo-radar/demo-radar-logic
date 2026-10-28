"""Coordinate one inference attempt using injected provider and journal objects.

InferenceService owns admission and active task lifetime. It does not own HTTP
routes, staff permissions, production records or scheduled jobs.
"""

import asyncio
import logging
import time

import httpx

from service.inference.identity import request_identity, source_identity
from service.inference.profiles import describe_profile
from service.inference.results import AttemptOutcome, build_result, fingerprint, utc_now
from service.inference.validation import validate_tags
from service.persistence.journal import AdmissionError
from service.providers.base import ProviderFailure
from service.tasks.limits import MAX_JOB_EVENTS, ExecutionLimits

logger = logging.getLogger(__name__)


class InferenceService:
    """Coordinate sequential attempts without coupling routes to SQL or a vendor.

    Args:
        settings: Runtime credentials, limits and mode.
        config: Approved prompt/model assets.
        journal: Durable admission and replay repository.
        provider: Object implementing TagProvider.predict(payload).

    A disconnect does not cancel admitted work. The lifecycle waits for active
    tasks; forced termination retains the journal's unresolved attempt marker.
    """

    task = "tagging"
    execution_limits = ExecutionLimits()

    def __init__(self, settings, config, journal, provider):
        self.settings, self.config = settings, config
        self.journal, self.provider = journal, provider
        self.active = set()

    async def suggest(self, request):
        """Return (saved response, HTTP status), dispatching at most one call.

        Input is a validated TagRequest. AdmissionError means no new call was
        admitted. A repeated request returns the original statistics. Request
        IDs cannot override the operator's attempt, batch or maintenance limits.
        """
        replay = self.replay(request)
        if replay is not None:
            return replay
        self.validate_profile(request)
        if request.model_id != self.config.version:
            raise AdmissionError("unsupported_configuration", 422)
        if self.settings.mode == "demo" and not request.event.id.startswith("synthetic-"):
            raise AdmissionError("synthetic_event_required", 422)
        identity = request_identity(request, self.config.sha256, self.settings.mode, self.task)
        event_key = self.attempt_key(request)
        return await self._admit(
            request,
            identity,
            event_key,
            lambda: self._infer(request, self.journal.attempt_count(event_key)),
            max_attempts=self.execution_limits.max_attempts,
        )

    def attempt_key(self, request):
        """Identify regular classifier work by source and configuration."""
        return fingerprint(
            {
                "event": request.event.model_dump(),
                "source": request.source_version,
                "config": self.config.sha256,
                "mode": self.settings.mode,
            }
        )

    def allowance_key(self, request):
        """Share regular task retries across provider/profile changes."""
        return fingerprint(
            {
                "task": self.task,
                "mode": self.settings.mode,
                "source": source_identity(request, self.task),
            }
        )

    def payload_for(self, request):
        """Build the pinned task payload used by reservation and execution."""
        return self.config.payload(
            request.event.title if self.task == "tagging" else request.snapshot
        )

    def validate_profile(self, request):
        """Validate explicit task/hash context without changing legacy request shapes."""
        context = request.execution
        if context is not None and (
            context.task != self.task or context.profile_sha256 != self.config.sha256
        ):
            raise AdmissionError("unsupported_task_profile", 422)

    def replay(self, request):
        """Replay original evidence even after its profile is no longer executable."""
        saved = self.journal.get_attempt(request.request_id)
        if saved is None:
            return None
        body, _ = saved
        execution = self.journal.execution(request.request_id)
        task = (
            execution["task"]
            if execution
            else ("daily-summary" if "snapshot_sha256" in body else "tagging")
        )
        if task != self.task or body.get("config_version", request.model_id) != request.model_id:
            raise AdmissionError("idempotency_conflict")
        sha = execution["profile_sha256"] if execution else body.get("config_sha256")
        mode = execution["mode"] if execution else body.get("mode")
        if sha is None:
            raise AdmissionError("attempt_unresolved")
        identity = request_identity(request, sha, mode, self.task)
        return self.journal.replay(request.request_id, identity)

    async def _admit(self, request, identity, event_key, execute, **options):
        """Hold the activity lock from reservation through final persistence.

        A saved replay releases the lock immediately. New work transfers it to
        the shielded task, so an HTTP disconnect cannot let recovery overlap
        inference. SQLite still decides admission and all attempt limits.
        """
        from service.persistence.locking import activity_lock
        from service.persistence.spending import policy

        lock = activity_lock(self.journal.path)
        lock.__enter__()
        try:
            payload = self.payload_for(request)
            approved = policy(self.settings, self.config)
            if approved is not None:
                try:
                    count = await asyncio.wait_for(self.provider.count_tokens(payload), timeout=5)
                except (ProviderFailure, TimeoutError) as exc:
                    raise AdmissionError("token_count_unavailable", 503) from exc
                approved = policy(
                    self.settings,
                    self.config,
                    input_tokens=count,
                    output_tokens=payload["max_completion_tokens"],
                )
            saved = self.journal.begin(
                request,
                identity,
                event_key,
                self.settings.min_interval_seconds,
                spending=approved,
                max_job_attempts=self.execution_limits.max_job_attempts,
                execution={
                    **describe_profile(self.task, self.config),
                    "mode": self.settings.mode,
                    "environment": self.settings.environment,
                    "origin": request.execution.origin if request.execution else "legacy",
                    "request_id": request.request_id,
                    "job_id": request.job_id,
                    "source_sha256": source_identity(request, self.task),
                    "attempt_limit": self.journal.max_attempts,
                    "payload_sha256": fingerprint(payload),
                    "timeout_seconds": self.settings.timeout_seconds
                    if self.task == "tagging"
                    else self.settings.summary_timeout_seconds,
                    "batch_event_limit": MAX_JOB_EVENTS,
                    "batch_attempt_limit": self.execution_limits.max_job_attempts,
                    "admitted_at": utc_now(),
                },
                allowance_key=self.allowance_key(request),
                **options,
            )
            if saved:
                result, status = saved
                lock.__exit__(None, None, None)
                return {**result, "replayed": True, "new_provider_calls": 0}, status

            async def recorded():
                self.journal.mark_execution(request.request_id, started_at=utc_now())
                logger.info(
                    "event=inference_phase task=%s request_id=%s phase=execute",
                    self.task,
                    request.request_id,
                )
                result = await execute()
                logger.info(
                    "event=inference_phase task=%s request_id=%s phase=saved outcome=%s",
                    self.task,
                    request.request_id,
                    result[0]["status"],
                )
                return result

            task = asyncio.create_task(recorded())
        except BaseException:
            lock.__exit__(None, None, None)
            raise
        self.active.add(task)
        task.add_done_callback(lambda task: self._finished_locked(task, lock))
        return await asyncio.shield(task)

    def _finished_locked(self, task, lock):
        """Release the lock even if a task was cancelled before it first ran."""
        try:
            self._finished(task)
        finally:
            lock.__exit__(None, None, None)

    async def _infer(self, request, attempt_number):
        """Execute, validate and save one attempt; never retry automatically.

        Args:
            request: Admitted TagRequest.
            attempt_number: Durable count including this attempt.
        Returns:
            (response dictionary, HTTP status) after successful persistence.
        Raises:
            Database errors leave admission blocked for operator recovery.
            Cancellation preserves the pre-dispatch marker, not a false failure.
        """
        started, wall_start = time.monotonic(), utc_now()
        outcome = AttemptOutcome()
        try:
            reply = await self._call_provider(
                request.request_id,
                self.provider.predict(self.config.payload(request.event.title)),
                self.settings.timeout_seconds,
            )
            validate_tags(reply.tags, reply.metadata)
            outcome.tags, outcome.metadata = reply.tags, reply.metadata
        except ProviderFailure as exc:
            outcome = AttemptOutcome(
                metadata=exc.metadata,
                state="unknown" if exc.unknown else "failed",
                code=exc.code,
                http_status=exc.status,
                retry_after=exc.retry_after,
            )
        except (TimeoutError, httpx.RequestError):
            outcome = AttemptOutcome(
                state="unknown", code="provider_outcome_unknown", http_status=504
            )
        # Cancellation intentionally propagates. The journal remains unresolved.
        result = build_result(
            request, self.config, self.settings, outcome, started, wall_start, attempt_number
        )
        self.journal.finish(
            request.request_id, result, outcome.http_status, outcome.state, outcome.retry_after
        )
        return result, outcome.http_status

    async def _call_provider(self, request_id, call, timeout):
        """Measure one bounded adapter call, including failures and cancellation."""
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout):
                return await call
        finally:
            self.journal.mark_execution(request_id, provider_seconds=time.monotonic() - started)

    def _finished(self, task):
        """Release task bookkeeping and consume errors after caller disconnect."""
        self.active.discard(task)
        if not task.cancelled():
            task.exception()

    async def close(self):
        """Wait for accepted tasks before the HTTP client closes; make no new calls."""
        if self.active:
            await asyncio.gather(*self.active, return_exceptions=True)
