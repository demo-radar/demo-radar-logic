"""Coordinate one inference attempt using injected provider and journal objects.

InferenceService owns admission and active task lifetime. It does not own HTTP
routes, staff permissions, production records or scheduled jobs.
"""

import asyncio
import time

import httpx

from service.inference.results import AttemptOutcome, build_result, fingerprint, utc_now
from service.persistence.journal import AdmissionError
from service.providers.base import ProviderFailure


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
        if request.model_id != self.config.version:
            raise AdmissionError("unsupported_configuration", 422)
        if self.settings.mode == "demo" and not request.event.id.startswith("synthetic-"):
            raise AdmissionError("synthetic_event_required", 422)
        identity = fingerprint(
            {
                "request": request.model_dump(),
                "config": self.config.sha256,
                "mode": self.settings.mode,
            }
        )
        event_key = fingerprint(
            {
                "event": request.event.model_dump(),
                "source": request.source_version,
                "config": self.config.sha256,
                "mode": self.settings.mode,
            }
        )
        return await self._admit(
            request,
            identity,
            event_key,
            lambda: self._infer(request, self.journal.attempt_count(event_key)),
        )

    async def _admit(self, request, identity, event_key, execute, **options):
        """Hold the activity lock from reservation through final persistence.

        A saved replay releases the lock immediately. New work transfers it to
        the shielded task, so an HTTP disconnect cannot let recovery overlap
        inference. SQLite still decides admission and all attempt limits.
        """
        from service.persistence.locking import activity_lock

        lock = activity_lock(self.journal.path)
        lock.__enter__()
        try:
            saved = self.journal.begin(
                request, identity, event_key, self.settings.min_interval_seconds, **options
            )
            if saved:
                result, status = saved
                lock.__exit__(None, None, None)
                return {**result, "replayed": True, "new_provider_calls": 0}, status
            task = asyncio.create_task(execute())
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
            async with asyncio.timeout(self.settings.timeout_seconds):
                reply = await self.provider.predict(self.config.payload(request.event.title))
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

    def _finished(self, task):
        """Release task bookkeeping and consume errors after caller disconnect."""
        self.active.discard(task)
        if not task.cancelled():
            task.exception()

    async def close(self):
        """Wait for accepted tasks before the HTTP client closes; make no new calls."""
        if self.active:
            await asyncio.gather(*self.active, return_exceptions=True)
