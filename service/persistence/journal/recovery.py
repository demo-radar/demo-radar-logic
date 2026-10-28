"""Audited unknown-outcome closure and the persistent maintenance gate."""

import json
import math
from datetime import UTC, datetime

from service.persistence.journal.exceptions import AdmissionError


class RecoveryStore:
    def __init__(self, connection):
        self.connection = connection

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
