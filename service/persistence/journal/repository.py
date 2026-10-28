"""Public facade for private journal records, admission and recovery.

Components share this object's connection factory. Each operation keeps its original
SQLite transaction boundary; no lock is held across provider network I/O.
"""

import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from service.persistence.journal.admission import AttemptAdmission
from service.persistence.journal.exceptions import AdmissionError
from service.persistence.journal.recovery import RecoveryStore
from service.persistence.journal.schema import JournalSchema
from service.persistence.spending import reconcile as reconcile_spending
from service.tasks.limits import MAX_JOB_ATTEMPTS


class Journal:
    """Own the private database connection and expose stable journal operations.

    Admission, schema upgrades and recovery have separate collaborators. They use
    the same connection factory, preserving saved identities, usage and locking.
    """

    def __init__(self, path: Path, *, max_attempts: int = 3):
        if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
            raise ValueError("Attempts per event must be 1–10")
        self.max_attempts = max_attempts
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        # Pre-create privately; SQLite sidecars inherit the database's mode.
        fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        path.chmod(0o600)
        JournalSchema(self.connection).upgrade()
        self._admission = AttemptAdmission(self.connection, self.max_attempts)
        self._recovery = RecoveryStore(self.connection)

    @contextmanager
    def connection(self):
        """Use short durable transactions; no lock is held across network I/O."""
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

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
        """Replay or reserve one attempt atomically through the admission component."""
        return self._admission.begin(
            request,
            identity,
            event_key,
            interval,
            event_id=event_id,
            max_attempts=max_attempts,
            max_job_attempts=max_job_attempts,
            execution=execution,
            allowance_key=allowance_key,
            spending=spending,
        )

    def finish(self, request_id, body, status_code, state, retry_after=0):
        """Commit result and raw usage before releasing request admission.

        Unknown outcomes retain the global block even when an error is returned.
        Long provider reset instructions persist across process restarts.

        Args:
            request_id: Previously reserved attempt ID.
            body: Validated JSON-safe response including usage/error evidence.
            status_code: Original API HTTP status for later replay.
            state: ok, failed or unknown. Only a started row may be completed.
            retry_after: Seconds of additional provider cooldown.
        Raises:
            AdmissionError: Attempt missing/already finalized; preserve its result.
            sqlite3.Error: Persistence failed; the unresolved marker stays active.
        """
        with self.connection() as db:
            changed = db.execute(
                "UPDATE attempts SET status=?, result=?, http_status=? WHERE request_id=? AND status='started'",
                (
                    state,
                    json.dumps(body, ensure_ascii=False, allow_nan=False),
                    status_code,
                    request_id,
                ),
            )
            if changed.rowcount != 1:
                raise AdmissionError("attempt_already_finalized")
            reconcile_spending(db, request_id, body, state)
            db.execute(
                "UPDATE control SET next_allowed=MAX(next_allowed, ?) WHERE id=1",
                (time.time() + retry_after,),
            )

    def attempt_count(self, event_key):
        """Return the durable attempt count for this exact event-input hash."""
        with self.connection() as db:
            return db.execute(
                "SELECT COUNT(*) FROM attempts WHERE event_key=?", (event_key,)
            ).fetchone()[0]

    def get_attempt(self, request_id):
        """Read one attempt without dispatch: (response, HTTP status), or None.

        Saved errors return HTTP 200 for a successful status lookup; their body
        retains the original outcome. Started records return HTTP 202. Filesystem
        permissions, not a database username/password, protect this SQLite file.
        """
        with self.connection() as db:
            row = db.execute("SELECT * FROM attempts WHERE request_id=?", (request_id,)).fetchone()
            resolution = db.execute(
                "SELECT resolved_at FROM attempt_resolutions WHERE request_id=?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        if row["result"] is not None:
            result = {**json.loads(row["result"]), "replayed": True, "new_provider_calls": 0}
            if resolution:
                # Add the operator decision to lookup only; keep the original
                # outcome, usage and private explanation unchanged in storage.
                result["resolution"] = {
                    "action": "abandoned_unknown",
                    "resolved_at": resolution["resolved_at"],
                }
            return result, 200
        return {
            "request_id": row["request_id"],
            "job_id": row["job_id"],
            "event_id": row["event_id"],
            "status": "unresolved",
            "started_at": row["started_at"],
            "usage_raw": None,
        }, 202

    def replay(self, request_id, identity):
        """Check original request identity before returning unchanged saved evidence."""
        with self.connection() as db:
            row = db.execute(
                "SELECT identity, result, http_status FROM attempts WHERE request_id=?",
                (request_id,),
            ).fetchone()
        if row is None or row["identity"] != identity:
            raise AdmissionError("idempotency_conflict")
        if row["result"] is None:
            raise AdmissionError("attempt_unresolved")
        body, _ = self.get_attempt(request_id)
        return body, row["http_status"]

    def execution(self, request_id):
        """Read private configuration/timing evidence without requiring its old assets."""
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM attempt_execution WHERE request_id=?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            **json.loads(row["snapshot"]),
            "execution_started_at": row["execution_started_at"],
            "provider_seconds": row["provider_seconds"],
        }

    def mark_execution(self, request_id, *, started_at=None, provider_seconds=None):
        """Persist measured phase boundaries without changing the pinned snapshot."""
        with self.connection() as db:
            if started_at is not None:
                db.execute(
                    "UPDATE attempt_execution SET execution_started_at=COALESCE(execution_started_at, ?) WHERE request_id=?",
                    (started_at, request_id),
                )
            if provider_seconds is not None:
                db.execute(
                    "UPDATE attempt_execution SET provider_seconds=? WHERE request_id=?",
                    (provider_seconds, request_id),
                )

    def retry_headers(self):
        """Return the remaining persisted cooldown for a replayed failure.

        The saved result retains the original delay for auditing. This header is
        calculated now, so replaying an old error never starts the wait again.
        """
        with self.connection() as db:
            deadline = db.execute("SELECT next_allowed FROM control WHERE id=1").fetchone()[0]
        seconds = math.ceil(deadline - time.time())
        return {"Retry-After": str(seconds)} if seconds > 0 else {}

    def close_unknown(self, request_id, *, operator, reason):
        """Record an audited closure while preserving the original unknown result."""
        return self._recovery.close_unknown(request_id, operator=operator, reason=reason)

    def recovery_status(self):
        """Read outstanding work and the remaining recovery wait."""
        return self._recovery.recovery_status()

    def maintenance(self, enabled=None):
        """Read or change drain mode; unresolved work prevents resuming."""
        return self._recovery.maintenance(enabled)
