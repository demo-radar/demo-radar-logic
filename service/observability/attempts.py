"""Read the authoritative attempt ledger without returning prompts or identities.

Request/job IDs are private correlation keys, never Prometheus labels. Cost
reconciliation is read live rather than copied into immutable model responses.
"""

import json
import re
from datetime import datetime


class AttemptMeasurements:
    """Export bounded pages through the journal's existing connection factory."""

    page_size = 100

    def __init__(self, journal):
        self.journal = journal

    def page(self, after=0):
        with self.journal.connection() as db:
            rows = db.execute(
                """SELECT change.cursor, a.*, e.snapshot, e.execution_started_at,
                   e.provider_seconds, s.reserved, s.charged, s.policy,
                   EXISTS(SELECT 1 FROM attempt_resolutions r WHERE r.request_id=a.request_id) AS unknown_closed,
                   EXISTS(SELECT 1 FROM spending_audit audit
                          WHERE audit.request_id=a.request_id) AS reconciled
                   FROM monitoring_changes change JOIN attempts a USING(request_id)
                   LEFT JOIN attempt_execution e USING(request_id)
                   LEFT JOIN spending s USING(request_id)
                   WHERE change.cursor > ? ORDER BY change.cursor LIMIT ?""",
                (after, self.page_size),
            ).fetchall()
            journal_id = db.execute(
                "SELECT journal_id FROM monitoring_identity WHERE id=1"
            ).fetchone()[0]
            latest = db.execute(
                "SELECT coalesce(max(cursor),0) FROM monitoring_changes"
            ).fetchone()[0]
        return {
            "schema_version": 1,
            "journal_id": journal_id,
            "attempts": [self.measure(row) for row in rows],
            "next_cursor": rows[-1]["cursor"] if rows else min(after, latest),
            "complete": len(rows) < self.page_size,
        }

    @staticmethod
    def measure(row):
        context = json.loads(row["snapshot"]) if row["snapshot"] else {}
        result = json.loads(row["result"]) if row["result"] else {}
        stats = result.get("statistics") or {}
        error = (result.get("error") or {}).get("code")
        known_response = bool(
            stats.get("returned_model")
            or stats.get("provider_request_id")
            or re.fullmatch(r"provider_http_[1-5][0-9]{2}", error or "")
        )
        mode = context.get("mode", result.get("mode", "unknown"))
        if mode == "demo" or stats.get("provider_call_occurred") is False:
            dispatch = "none"
        elif known_response:
            dispatch = "confirmed"
        elif row["execution_started_at"]:
            dispatch = "possible"
        else:
            dispatch = "unconfirmed"
        price = json.loads(row["policy"]) if row["policy"] else {}
        if row["reconciled"]:
            cost_state = "reconciled"
        elif row["charged"] is not None:
            cost_state = "estimated"
        elif price:
            cost_state = "awaiting_reconciliation"
        else:
            cost_state = "unavailable"
        return {
            "request_id": row["request_id"],
            "job_id": row["job_id"],
            "task": context.get("task", "unknown"),
            "provider": context.get("provider") or stats.get("provider") or "unknown",
            "model": context.get("model") or stats.get("requested_model") or "unknown",
            "profile": context.get("profile_id") or result.get("config_version") or "unknown",
            "profile_sha256": context.get("profile_sha256"),
            "source_sha256": context.get("source_sha256"),
            "instructions_sha256": context.get("instructions_sha256"),
            "environment": context.get("environment", "unspecified"),
            "origin": context.get("origin", "legacy"),
            "mode": "synthetic" if mode == "demo" else mode,
            "outcome": row["status"],
            "unknown_closed": bool(row["unknown_closed"]),
            "dispatch": dispatch,
            "error_code": error,
            "started_at": row["started_at"],
            "finished_at": stats.get("finished_at"),
            "queue_seconds": elapsed(context.get("admitted_at"), row["execution_started_at"]),
            "provider_seconds": seconds(row["provider_seconds"]),
            "attempt_seconds": elapsed(row["started_at"], stats.get("finished_at")),
            **{
                name: count(stats.get(name))
                for name in (
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "cached_input_tokens",
                    "reasoning_tokens",
                )
            },
            "currency": price.get("currency"),
            "pricing_version": price.get("version"),
            "reserved_microusd": row["reserved"],
            "charged_microusd": row["charged"],
            "cost_state": cost_state,
        }


def count(value):
    return value if type(value) is int and value >= 0 else None


def seconds(value):
    return value if type(value) in (int, float) and 0 <= value <= 86400 else None


def elapsed(start, end):
    if not start or not end:
        return None
    try:
        return seconds(
            (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        )
    except (ValueError, TypeError):
        return None
