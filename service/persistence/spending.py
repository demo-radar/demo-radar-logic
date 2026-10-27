"""Reserve paid calls in the same durable transaction as request admission."""

import json
import math
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from service.providers.models import MODEL_CATALOG


def money(value):
    """Accept exact USD amounts with at most six decimal places, never floats."""
    try:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,6})?", value):
            raise TypeError("Use a plain USD amount with at most six decimal places")
        amount = Decimal(value)
        micros = amount * 1000000
        if not amount.is_finite() or amount < 0 or micros != micros.to_integral_value():
            raise ValueError("Invalid USD amount")
        return int(micros)
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid USD amount") from None


def cost(input_tokens, output_tokens, price):
    return math.ceil(
        Decimal(price["input_microusd_per_token"]) * input_tokens
        + Decimal(price["output_microusd_per_token"]) * output_tokens
    )


def policy(settings, config, *, input_tokens=None, output_tokens=None):
    """Return a complete operator-approved policy, or refuse before admission."""
    from service.persistence.journal import AdmissionError

    if settings.mode != "live":
        return None
    model = MODEL_CATALOG.get(config.model)
    if model is None or model.provider != config.provider:
        raise AdmissionError("pricing_review_required", 503)
    if model.requires_free_account:
        if (
            config.provider != "hetzner"
            or not settings.provider_key
            or not settings.free_tier_confirmed
        ):
            raise AdmissionError("provider_disabled", 503)
        return None
    if config.provider != "gemini" or not settings.gemini_enabled or not settings.gemini_key:
        raise AdmissionError("provider_disabled", 503)
    try:
        limits = [
            money(value)
            for value in (
                settings.paid_run_usd,
                settings.paid_period_usd,
                settings.paid_account_usd,
            )
        ]
    except ValueError:
        raise AdmissionError("spending_not_configured", 503) from None
    if not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,120}", settings.paid_account) or not all(
        0 < value <= 10**12 for value in limits
    ):
        raise AdmissionError("spending_not_configured", 503)
    price = model.pricing
    if price is None or price["currency"] != "USD" or price["model"] != config.model:
        raise AdmissionError("pricing_review_required", 503)
    today = datetime.now(UTC).date().isoformat()
    if not price["valid_from"] <= today <= price["valid_until"]:
        raise AdmissionError("pricing_review_required", 503)
    reserved_input = price["maximum_input_tokens"]
    reserved_output = price["maximum_output_tokens"]
    if input_tokens is not None:
        # Count the full native request; allow extra protocol tokens, never chars/4.
        if type(input_tokens) is not int or not 0 <= input_tokens <= reserved_input:
            raise AdmissionError("token_count_unavailable", 503)
        reserved_input = min(reserved_input, input_tokens + 1024)
        reserved_output = output_tokens
        if (
            type(reserved_output) is not int
            or not 1 <= reserved_output <= price["maximum_output_tokens"]
        ):
            raise AdmissionError("pricing_review_required", 503)
    return {
        **price,
        "account": settings.paid_account,
        "period": today,
        "run_limit": limits[0],
        "period_limit": limits[1],
        "account_limit": limits[2],
        "reservation": cost(reserved_input, reserved_output, price),
        "reserved_input_tokens": reserved_input,
        "reserved_output_tokens": reserved_output,
        "counted_input_tokens": input_tokens,
    }


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS spending (
        request_id TEXT PRIMARY KEY REFERENCES attempts(request_id), job_id TEXT NOT NULL,
        account TEXT NOT NULL, period TEXT NOT NULL, reserved INTEGER NOT NULL CHECK(reserved >= 0),
        charged INTEGER CHECK(charged >= 0), policy TEXT NOT NULL, review_required INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS spending_period ON spending(period, account)")
    db.execute("CREATE INDEX IF NOT EXISTS spending_job ON spending(job_id)")
    db.execute("""CREATE TABLE IF NOT EXISTS spending_audit (
        id INTEGER PRIMARY KEY, request_id TEXT NOT NULL REFERENCES spending(request_id),
        operator TEXT NOT NULL, reason TEXT NOT NULL, previous INTEGER, charged INTEGER NOT NULL,
        recorded_at TEXT NOT NULL
    )""")


def reserve(db, request, approved, *, summary_allowance=None):
    """Share run and UTC-day ceilings across tasks, profiles, retries and restarts."""
    from service.persistence.journal import AdmissionError

    if approved is None:
        return
    if db.execute(
        "SELECT 1 FROM spending s WHERE (review_required=1 OR charged > reserved) AND NOT EXISTS (SELECT 1 FROM spending_audit a WHERE a.request_id=s.request_id) LIMIT 1"
    ).fetchone():
        raise AdmissionError("spending_review_required", 503)
    # Radar creates a new pinned job when a summary provider changes. Keep
    # spending for the same source under its original run ceiling across jobs.
    rows = db.execute(
        "SELECT s.*, e.allowance_key FROM spending s "
        "LEFT JOIN attempt_execution e USING(request_id) "
        "WHERE s.period=? OR s.job_id=? OR s.charged IS NULL OR e.allowance_key=?",
        (approved["period"], request.job_id, summary_allowance),
    ).fetchall()
    for name, subset in (
        (
            "run_limit",
            [
                row
                for row in rows
                if row["job_id"] == request.job_id
                or summary_allowance is not None
                and row["allowance_key"] == summary_allowance
            ],
        ),
        (
            "period_limit",
            [
                row
                for row in rows
                if (row["period"] == approved["period"] or row["charged"] is None)
            ],
        ),
        (
            "account_limit",
            [
                row
                for row in rows
                if (row["period"] == approved["period"] or row["charged"] is None)
                and row["account"] == approved["account"]
            ],
        ),
    ):
        # Raising an environment limit cannot loosen an already started allowance.
        ceiling = min([approved[name], *[json.loads(row["policy"])[name] for row in subset]])
        used = sum(row["reserved"] if row["charged"] is None else row["charged"] for row in subset)
        if used + approved["reservation"] > ceiling:
            raise AdmissionError("spending_limit", 429)
    db.execute(
        "INSERT INTO spending(request_id,job_id,account,period,reserved,charged,policy) VALUES(?,?,?,?,?,NULL,?)",
        (
            request.request_id,
            request.job_id,
            approved["account"],
            approved["period"],
            approved["reservation"],
            json.dumps(approved),
        ),
    )


def reconcile(db, request_id, result, state):
    """Unknown or incomplete usage retains its reservation; failure is not free."""
    row = db.execute("SELECT * FROM spending WHERE request_id=?", (request_id,)).fetchone()
    if row is None or state == "unknown":
        return
    stats = result.get("statistics") or {}
    price = json.loads(row["policy"])
    returned = stats.get("returned_model")
    if returned != price["model"]:
        if returned is not None:
            db.execute("UPDATE spending SET review_required=1 WHERE request_id=?", (request_id,))
        return
    counts = [stats.get(name) for name in ("input_tokens", "output_tokens", "total_tokens")]
    if any(type(value) is not int or value < 0 for value in counts) or counts[2] != sum(counts[:2]):
        return
    if counts[0] > price.get("reserved_input_tokens", price["maximum_input_tokens"]) or counts[
        1
    ] > price.get("reserved_output_tokens", price["maximum_output_tokens"]):
        db.execute("UPDATE spending SET review_required=1 WHERE request_id=?", (request_id,))
        return
    charged = cost(*counts[:2], price)
    # Reconcile only complete counts within the published model bounds.
    db.execute("UPDATE spending SET charged=? WHERE request_id=?", (charged, request_id))


def inspect(db, request_id):
    """Return private cost evidence without credentials or generated content."""
    from service.persistence.journal import AdmissionError

    row = db.execute("SELECT * FROM spending WHERE request_id=?", (request_id,)).fetchone()
    if row is None:
        raise AdmissionError("not_found", 404)
    price = json.loads(row["policy"])
    return {
        "request_id": request_id,
        "currency": "USD",
        "reserved_microusd": row["reserved"],
        "charged_microusd": row["charged"],
        "pricing_version": price["version"],
        "period": row["period"],
        "awaiting_reconciliation": row["charged"] is None,
        "review_required": bool(row["review_required"]),
    }


def settle(db, request_id, amount_usd, operator, reason):
    """Record verified account evidence without changing the original model result."""
    from service.persistence.journal import AdmissionError

    try:
        charged = money(amount_usd)
    except ValueError:
        raise AdmissionError("invalid_request", 422) from None
    if charged > 10**12:
        raise AdmissionError("invalid_request", 422)
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        "SELECT s.*, a.status FROM spending s JOIN attempts a USING(request_id) WHERE s.request_id=?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise AdmissionError("not_found", 404)
    if row["status"] == "started" or (
        row["status"] == "unknown"
        and not db.execute(
            "SELECT 1 FROM attempt_resolutions WHERE request_id=?", (request_id,)
        ).fetchone()
    ):
        raise AdmissionError("attempt_unresolved")
    # Lost replies can repeat the identical decision, without creating another audit entry.
    previous = db.execute(
        "SELECT * FROM spending_audit WHERE request_id=? ORDER BY id DESC LIMIT 1", (request_id,)
    ).fetchone()
    if (
        previous
        and previous["charged"] == charged
        and previous["operator"] == operator
        and previous["reason"] == reason
    ):
        return inspect(db, request_id)
    db.execute(
        "INSERT INTO spending_audit(request_id,operator,reason,previous,charged,recorded_at) VALUES(?,?,?,?,?,?)",
        (request_id, operator, reason, row["charged"], charged, datetime.now(UTC).isoformat()),
    )
    db.execute(
        "UPDATE spending SET charged=?, review_required=0 WHERE request_id=?", (charged, request_id)
    )
    return inspect(db, request_id)
