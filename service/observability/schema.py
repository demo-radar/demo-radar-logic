"""An additive change cursor for read-only monitoring consumers.

SQLite triggers also observe writes from compatible older controllers. Only the
latest measurement cursor is replaced; inference attempts and audit history are
never replaced. Replays and reads do not advance the cursor.
"""

from uuid import uuid4


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS monitoring_identity (
        id INTEGER PRIMARY KEY CHECK(id=1), journal_id TEXT NOT NULL)""")
    db.execute("INSERT OR IGNORE INTO monitoring_identity VALUES(1,?)", (str(uuid4()),))
    db.execute("""CREATE TABLE IF NOT EXISTS monitoring_changes (
        cursor INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE)""")
    for table in (
        "attempts",
        "attempt_execution",
        "spending",
        "spending_audit",
        "attempt_resolutions",
    ):
        for action in ("INSERT", "UPDATE"):
            # Table and trigger identifiers come only from the fixed tuples above.
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS monitoring_{table}_{action.lower()}
                AFTER {action} ON {table} BEGIN
                  INSERT OR REPLACE INTO monitoring_changes(request_id) VALUES(NEW.request_id);
                END""")
    db.execute("""INSERT OR IGNORE INTO monitoring_changes(request_id)
        SELECT request_id FROM attempts ORDER BY rowid""")
