"""Private durable request admission, result replay and maintenance state.

SQLite transactions coordinate processes sharing this file on one host. Deploy
one container with one Uvicorn worker for now. Separate hosts or network-file
SQLite are not supported; distributed admission remains backend integration work.
Never clear a started/unknown request automatically on startup: a provider may
still be running after a crash. Reconcile it before accepting new inference.
"""

import hashlib
import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class AdmissionError(Exception):
    """Safe, structured rejection that contains no title, token or server body."""

    def __init__(self, code, status=409, retry_after=None):
        self.code, self.status, self.retry_after = code, status, retry_after


class Journal:
    """Repository for a private local SQLite file; no database login is needed.

    Args:
        path: Persistent local file, protected by OS permissions (0600).
        max_attempts: Operator ceiling per event input, default 3, range 1–10.

    All SQL stays here. control stores maintenance/pacing; attempts stores replay
    and usage evidence. Staff users, jobs and approved tags belong to Demo Radar.
    Schema upgrades add indexes, write guards and recovery records without rebuilding old tables.
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
        self._initialize()

    def _initialize(self):
        """Upgrade indexes, guards and recovery records without changing saved results.

        Older journals gain indexes, triggers, a recovery audit table and a version marker.
        No table is rebuilt and no existing result is changed. Guards validate
        future writes. A newer schema fails startup instead of being downgraded.
        """
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError("Unsupported journal schema version")
            db.execute("""CREATE TABLE IF NOT EXISTS control (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                maintenance INTEGER NOT NULL DEFAULT 0,
                next_allowed REAL NOT NULL DEFAULT 0
            )""")
            db.execute("INSERT OR IGNORE INTO control(id) VALUES(1)")
            db.execute("""CREATE TABLE IF NOT EXISTS attempts (
                request_id TEXT PRIMARY KEY, identity TEXT NOT NULL,
                event_key TEXT NOT NULL, event_id TEXT NOT NULL,
                job_id TEXT NOT NULL, status TEXT NOT NULL,
                result TEXT, http_status INTEGER, started_at TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS attempt_resolutions (
                request_id TEXT PRIMARY KEY REFERENCES attempts(request_id),
                operator TEXT NOT NULL, reason TEXT NOT NULL, resolved_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS attempts_event ON attempts(event_key, status)")
            db.execute("CREATE INDEX IF NOT EXISTS attempts_job ON attempts(job_id, event_id)")
            db.execute("CREATE INDEX IF NOT EXISTS attempts_status ON attempts(status)")
            if version < 2:
                for operation in ("insert", "update"):
                    db.execute(f"DROP TRIGGER IF EXISTS attempts_guard_{operation}")
            for operation in ("INSERT", "UPDATE"):
                # The SQL identifiers below come from this fixed internal tuple.
                db.execute(f"""CREATE TRIGGER IF NOT EXISTS attempts_guard_{operation.lower()}
                    BEFORE {operation} ON attempts BEGIN
                    SELECT CASE WHEN NEW.request_id IS NULL
                        OR NEW.status NOT IN ('started','ok','failed','unknown')
                        OR (NEW.status = 'started' AND (NEW.result IS NOT NULL OR NEW.http_status IS NOT NULL))
                        OR (NEW.status != 'started' AND (NEW.result IS NULL OR NEW.http_status IS NULL
                            OR NEW.http_status NOT BETWEEN 100 AND 599))
                        THEN RAISE(ABORT, 'Invalid attempt state') END;
                    SELECT CASE WHEN NEW.status IN ('started','unknown') AND EXISTS (
                        SELECT 1 FROM attempts WHERE status IN ('started','unknown')
                        AND request_id != NEW.request_id
                        AND request_id NOT IN (SELECT request_id FROM attempt_resolutions))
                        THEN RAISE(ABORT, 'Another unresolved attempt exists') END;
                    END""")
                db.execute(f"""CREATE TRIGGER IF NOT EXISTS control_guard_{operation.lower()}
                    BEFORE {operation} ON control
                    WHEN NEW.maintenance NOT IN (0,1) OR NEW.next_allowed < 0
                    BEGIN SELECT RAISE(ABORT, 'Invalid control state'); END""")
            # Additive side table: older binaries can still read and replay attempts.
            db.execute("""CREATE TABLE IF NOT EXISTS attempt_execution (
                request_id TEXT PRIMARY KEY REFERENCES attempts(request_id),
                allowance_key TEXT NOT NULL, snapshot TEXT NOT NULL,
                execution_started_at TEXT, provider_seconds REAL
            )""")
            db.execute(
                "CREATE INDEX IF NOT EXISTS execution_allowance ON attempt_execution(allowance_key)"
            )
            db.execute("""CREATE TRIGGER IF NOT EXISTS execution_snapshot_immutable
                BEFORE UPDATE OF snapshot, allowance_key ON attempt_execution
                BEGIN SELECT RAISE(ABORT, 'Execution snapshot is immutable'); END""")
            self._backfill_execution(db)
            db.execute("PRAGMA user_version = 2")

    @staticmethod
    def _backfill_execution(db):
        """Recover only identities actually recorded by older service versions."""
        rows = db.execute(
            "SELECT a.* FROM attempts a LEFT JOIN attempt_execution e USING(request_id) WHERE e.request_id IS NULL AND a.result IS NOT NULL"
        ).fetchall()
        for row in rows:
            try:
                body = json.loads(row["result"])
                task = "daily-summary" if "snapshot_sha256" in body else "tagging"
                source = body["snapshot_sha256" if task == "daily-summary" else "input_sha256"]
                mode, version, sha = body["mode"], body["config_version"], body["config_sha256"]
                if not all(isinstance(v, str) and v for v in (source, mode, version, sha)):
                    continue
                stats = body.get("statistics") or {}
                context = {
                    "task": task,
                    "source_sha256": source,
                    "mode": mode,
                    "profile_id": version,
                    "profile_sha256": sha,
                    "provider": stats.get("provider"),
                    "model": stats.get("requested_model"),
                    "origin": "legacy",
                    "environment": "unspecified",
                    "request_id": row["request_id"],
                    "job_id": row["job_id"],
                    "admitted_at": row["started_at"],
                    "evidence": "legacy-result",
                }
                allowance = hashlib.sha256(
                    json.dumps(
                        {"task": task, "mode": mode, "source": source},
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                db.execute(
                    "INSERT INTO attempt_execution(request_id, allowance_key, snapshot) VALUES(?,?,?)",
                    (row["request_id"], allowance, json.dumps(context, allow_nan=False)),
                )
            except (KeyError, TypeError, ValueError):
                # Old partial evidence remains readable; never invent its profile/usage.
                continue

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
        execution=None,
        allowance_key=None,
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
        Returns:
            Saved (response, HTTP status) for a replay, or None after reservation.
        Raises:
            AdmissionError: Busy, conflicting, paused or exhausted work; no call.
        """
        event_id = event_id if event_id is not None else request.event.id
        attempt_limit = (
            self.max_attempts if max_attempts is None else min(self.max_attempts, max_attempts)
        )
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM attempts WHERE request_id=?", (request.request_id,)
            ).fetchone()
            if previous:
                if previous["identity"] != identity:
                    raise AdmissionError("idempotency_conflict")
                if previous["result"] is not None:
                    return json.loads(previous["result"]), previous["http_status"]
                raise AdmissionError("attempt_unresolved")
            control = db.execute("SELECT * FROM control WHERE id=1").fetchone()
            if control["maintenance"]:
                raise AdmissionError("maintenance", 503)
            if db.execute(
                "SELECT 1 FROM attempts WHERE status IN ('started','unknown') AND request_id NOT IN (SELECT request_id FROM attempt_resolutions) LIMIT 1"
            ).fetchone():
                raise AdmissionError("inference_busy_or_recovery_required")
            now = time.time()
            if control["next_allowed"] > now:
                raise AdmissionError(
                    "provider_pacing", 429, math.ceil(control["next_allowed"] - now)
                )
            if db.execute(
                "SELECT 1 FROM attempts a JOIN attempt_resolutions r USING(request_id) WHERE a.event_key=?",
                (event_key,),
            ).fetchone():
                raise AdmissionError("event_outcome_closed_unknown")
            prior = db.execute(
                "SELECT status FROM attempts WHERE event_key=?", (event_key,)
            ).fetchall()
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
            saved_limits = db.execute(
                "SELECT e.snapshot FROM attempts a JOIN attempt_execution e USING(request_id) WHERE a.job_id=?",
                (request.job_id,),
            ).fetchall()
            for saved in saved_limits:
                limit = json.loads(saved["snapshot"]).get("attempt_limit")
                if type(limit) is int:
                    attempt_limit = min(attempt_limit, limit)
            if execution is not None:
                execution = {**execution, "attempt_limit": attempt_limit}
            if used >= attempt_limit:
                raise AdmissionError("event_attempt_limit", 429)
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
            if len(batch) >= 120 or (
                event_id not in {row["event_id"] for row in batch}
                and len({row["event_id"] for row in batch}) >= 40
            ):
                raise AdmissionError("batch_limit", 429)
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
            db.execute("UPDATE control SET next_allowed=? WHERE id=1", (now + interval,))
        return None

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
        """Record an operator's decision to abandon an old unknown result.

        Run under an exclusive activity/offline lock with maintenance enabled. This
        preserves the saved response and attempt count. Its exact input remains
        blocked; unrelated work may resume. Nothing is marked successful.

        Args:
            request_id: A finalized unknown attempt, at least 15 minutes old.
            operator: Non-empty local operator name for the audit record.
            reason: Explanation of the investigation and decision (no secrets).
        Returns:
            The saved resolution. Repeating the same decision is safe.
        Raises:
            AdmissionError: Not paused, unfinished/recent work, or conflicting decision.
        """
        if not isinstance(operator, str) or not 1 <= len(operator.strip()) <= 160:
            raise ValueError("Supply an operator name")
        if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 1000:
            raise ValueError("Supply a recovery explanation of 10–1000 characters")
        operator, reason = operator.strip(), reason.strip()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT maintenance FROM control WHERE id=1").fetchone()[0]:
                raise AdmissionError("maintenance_required")
            row = db.execute("SELECT * FROM attempts WHERE request_id=?", (request_id,)).fetchone()
            if row is None or row["status"] != "unknown" or row["result"] is None:
                raise AdmissionError("attempt_not_finalized_unknown")
            saved = db.execute(
                "SELECT * FROM attempt_resolutions WHERE request_id=?", (request_id,)
            ).fetchone()
            if saved:
                if saved["operator"] != operator or saved["reason"] != reason:
                    raise AdmissionError("resolution_conflict")
                return dict(saved)
            try:
                body = json.loads(row["result"])
                finished = datetime.fromisoformat(body["statistics"]["finished_at"])
                if finished.tzinfo is None or (datetime.now(UTC) - finished).total_seconds() < 900:
                    raise AdmissionError("recovery_wait_required")
            except (KeyError, TypeError, ValueError):
                raise AdmissionError("attempt_not_finalized_unknown") from None
            db.execute(
                "INSERT INTO attempt_resolutions VALUES(?,?,?,?)",
                (request_id, operator, reason, datetime.now(UTC).isoformat()),
            )
            return dict(
                db.execute(
                    "SELECT * FROM attempt_resolutions WHERE request_id=?", (request_id,)
                ).fetchone()
            )

    def recovery_status(self):
        """Describe the unresolved gate without exposing titles or provider bodies.

        A saved timeout becomes eligible for explicit closure after 15 minutes.
        A started marker from a crash needs investigation; age alone cannot
        establish that its remote call has ended.
        """
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM attempts WHERE status IN ('started','unknown') "
                "AND request_id NOT IN (SELECT request_id FROM attempt_resolutions)"
            ).fetchall()
        items = []
        for row in rows:
            body = json.loads(row["result"]) if row["result"] else {}
            remaining = None
            try:
                finished = datetime.fromisoformat(body["statistics"]["finished_at"])
                if finished.tzinfo is not None:
                    remaining = max(
                        0, math.ceil(900 - (datetime.now(UTC) - finished).total_seconds())
                    )
            except (KeyError, TypeError, ValueError):
                pass
            items.append(
                {
                    "request_id": row["request_id"],
                    "status": row["status"],
                    "task": "summary" if row["event_id"].startswith("daily-") else "tagging",
                    "wait_seconds": remaining,
                    "can_close": row["status"] == "unknown" and remaining == 0,
                }
            )
        return {"items": items}

    def maintenance(self, enabled=None):
        """Persist drain mode; resuming is blocked until uncertain work is resolved."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT COUNT(*) FROM attempts WHERE status IN ('started','unknown') AND request_id NOT IN (SELECT request_id FROM attempt_resolutions)"
            ).fetchone()[0]
            if enabled is False and active:
                raise AdmissionError("inference_busy_or_recovery_required")
            if enabled is not None:
                db.execute("UPDATE control SET maintenance=? WHERE id=1", (int(enabled),))
            state = db.execute("SELECT maintenance FROM control WHERE id=1").fetchone()[0]
        return {"maintenance": bool(state), "unresolved_attempts": active, "drained": not active}
