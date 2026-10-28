"""Replay checks and atomic admission into the journal's shared execution lane."""

import json
import math
import time
from datetime import UTC, datetime

from service.execution import MAX_JOB_ATTEMPTS, MAX_JOB_EVENTS
from service.persistence.exceptions import AdmissionError
from service.persistence.spending import reserve as reserve_spending


class AttemptAdmission:
    """Keep all gates, attempt writes and paid reservations in one transaction."""

    def __init__(self, connection, max_attempts):
        self.connection, self.max_attempts = connection, max_attempts

    def begin(
        self,
        request,
        identity,
        event_key,
        interval,
        *,
        event_id=None,
        max_attempts=None,
        max_job_attempts=MAX_JOB_ATTEMPTS,
        execution=None,
        allowance_key=None,
        spending=None,
    ):
        """Atomically replay or reserve one attempt, enforcing persisted caps.

        Busy, maintenance, pacing and exhausted limits make no provider call.
        Event counts survive jobs and restarts. Failed attempts use the same
        allowance; a successful event must not be sent again with another key.

        Args:
            request: Validated request with stable event/job/request identifiers.
            identity: Hash of request, configuration and execution mode.
            event_key: Hash identifying the event input across jobs.
            interval: Minimum seconds before the next dispatch.
            event_id: Optional daily snapshot ID for summary work.
            max_attempts: Optional tighter server-side cap; never raises the limit.
            max_job_attempts: Server-side job cap, one for an explicit Gem execution.
                Enforced across all request IDs, events and historical scope formats.
        Returns:
            Saved (response, HTTP status) for a replay, or None after reservation.
        Raises:
            AdmissionError: Busy, conflicting, paused or exhausted work; no call.
        """
        if type(max_job_attempts) is not int or not 1 <= max_job_attempts <= MAX_JOB_ATTEMPTS:
            raise ValueError(f"Job attempts must be 1–{MAX_JOB_ATTEMPTS}")
        event_id = event_id if event_id is not None else request.event.id
        attempt_limit = (
            self.max_attempts if max_attempts is None else min(self.max_attempts, max_attempts)
        )
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            saved = self._replay(db, request, identity)
            if saved is not None:
                return saved
            now = self._check_gate(db)
            used = self._source_attempts(db, event_key, allowance_key)
            saved_limits = db.execute(
                "SELECT e.snapshot FROM attempts a JOIN attempt_execution e USING(request_id) WHERE a.job_id=?",
                (request.job_id,),
            ).fetchall()
            for saved in saved_limits:
                snapshot = json.loads(saved["snapshot"])
                limit = snapshot.get("attempt_limit")
                if type(limit) is int:
                    attempt_limit = min(attempt_limit, limit)
                job_limit = snapshot.get("batch_attempt_limit")
                if type(job_limit) is int:
                    max_job_attempts = min(max_job_attempts, job_limit)
            if execution is not None:
                execution = {
                    **execution,
                    "attempt_limit": attempt_limit,
                    "batch_attempt_limit": max_job_attempts,
                }
            if used >= attempt_limit:
                raise AdmissionError("event_attempt_limit", 429)
            self._check_job(db, request, execution, event_id, max_job_attempts)
            db.execute(
                "INSERT INTO attempts VALUES(?,?,?,?,?,'started',NULL,NULL,?)",
                (
                    request.request_id,
                    identity,
                    event_key,
                    event_id,
                    request.job_id,
                    datetime.now(UTC).isoformat(),
                ),
            )
            if execution is not None:
                db.execute(
                    "INSERT INTO attempt_execution(request_id, allowance_key, snapshot) VALUES(?,?,?)",
                    (request.request_id, allowance_key, json.dumps(execution, allow_nan=False)),
                )
            reserve_spending(
                db,
                request,
                spending,
                summary_allowance=(
                    allowance_key if execution and execution["task"] == "daily-summary" else None
                ),
            )
            db.execute("UPDATE control SET next_allowed=? WHERE id=1", (now + interval,))
        return None

    @staticmethod
    def _replay(db, request, identity):
        previous = db.execute(
            "SELECT * FROM attempts WHERE request_id=?", (request.request_id,)
        ).fetchone()
        if previous:
            if previous["identity"] != identity:
                raise AdmissionError("idempotency_conflict")
            if previous["result"] is not None:
                return json.loads(previous["result"]), previous["http_status"]
            raise AdmissionError("attempt_unresolved")
        return None

    @staticmethod
    def _check_gate(db):
        control = db.execute("SELECT * FROM control WHERE id=1").fetchone()
        if control["maintenance"]:
            raise AdmissionError("maintenance", 503)
        if db.execute(
            "SELECT 1 FROM attempts WHERE status IN ('started','unknown') AND request_id NOT IN (SELECT request_id FROM attempt_resolutions) LIMIT 1"
        ).fetchone():
            raise AdmissionError("inference_busy_or_recovery_required")
        now = time.time()
        if control["next_allowed"] > now:
            raise AdmissionError("provider_pacing", 429, math.ceil(control["next_allowed"] - now))
        return now

    @staticmethod
    def _source_attempts(db, event_key, allowance_key):
        if db.execute(
            "SELECT 1 FROM attempts a JOIN attempt_resolutions r USING(request_id) WHERE a.event_key=?",
            (event_key,),
        ).fetchone():
            raise AdmissionError("event_outcome_closed_unknown")
        prior = db.execute("SELECT status FROM attempts WHERE event_key=?", (event_key,)).fetchall()
        if any(row["status"] == "ok" for row in prior):
            raise AdmissionError("event_already_completed_use_original_request")
        if allowance_key is not None:
            shared = db.execute(
                "SELECT a.status, r.request_id AS resolved FROM attempts a "
                "JOIN attempt_execution e USING(request_id) "
                "LEFT JOIN attempt_resolutions r USING(request_id) WHERE e.allowance_key=?",
                (allowance_key,),
            ).fetchall()
            if any(row["resolved"] for row in shared):
                raise AdmissionError("event_outcome_closed_unknown")
            # Config-aware reuse stays separate from the shared retry allowance.
            used = (
                len(shared)
                + db.execute(
                    "SELECT COUNT(*) FROM attempts a LEFT JOIN attempt_execution e USING(request_id) "
                    "WHERE a.event_key=? AND e.request_id IS NULL",
                    (event_key,),
                ).fetchone()[0]
            )
        else:
            used = len(prior)
        return used

    @staticmethod
    def _check_job(db, request, execution, event_id, max_job_attempts):
        if execution is not None:
            pinned = db.execute(
                "SELECT e.snapshot FROM attempts a JOIN attempt_execution e USING(request_id) WHERE a.job_id=? LIMIT 1",
                (request.job_id,),
            ).fetchone()
            if pinned is not None and any(
                json.loads(pinned["snapshot"])[key] != execution[key]
                for key in (
                    "task",
                    "profile_id",
                    "profile_sha256",
                    "mode",
                    "origin",
                    "environment",
                )
            ):
                raise AdmissionError("job_configuration_mismatch")
        batch = db.execute(
            "SELECT event_id FROM attempts WHERE job_id=?", (request.job_id,)
        ).fetchall()
        if len(batch) >= max_job_attempts or (
            event_id not in {row["event_id"] for row in batch}
            and len({row["event_id"] for row in batch}) >= MAX_JOB_EVENTS
        ):
            raise AdmissionError("batch_limit", 429)
