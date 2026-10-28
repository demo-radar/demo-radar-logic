"""Additive journal schema upgrades; original attempts and results stay intact."""

import hashlib
import json

from service.persistence.spending import initialize as initialize_spending


class JournalSchema:
    def __init__(self, connection):
        self.connection = connection

    def upgrade(self):
        """Upgrade indexes, guards and recovery records without changing saved results.

        Older journals gain indexes, triggers, a recovery audit table and a version marker.
        No table is rebuilt and no existing result is changed. Guards validate
        future writes. A newer schema fails startup instead of being downgraded.
        """
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3):
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
            initialize_spending(db)
            db.execute("PRAGMA user_version = 3")

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
