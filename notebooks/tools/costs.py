"""Private attempt audit and restart-safe reservations for paid notebook experiments.

These helpers do not send requests or decide models. Notebook adapters must reserve
before every HTTP attempt, including retries, using a defensible maximum charge.
"""

import json
import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from decimal import ROUND_CEILING, Decimal
from pathlib import Path


def cost_microusd(
    input_tokens,
    output_tokens,
    input_per_million,
    output_per_million,
    *,
    tool_calls=0,
    tool_price_usd="0",
):
    """Return a conservative USD-millionth estimate for explicit token/tool bounds.

    Output tokens must include reasoning tokens. Input bounds must include billed
    retrieved context. Prices are supplied from a dated provider price record;
    this calculation does not establish that the provider enforces these bounds.
    Missing/negative/nonfinite inputs fail rather than being priced as zero.
    """
    for value in (input_tokens, output_tokens, tool_calls):
        if type(value) is not int or value < 0:
            raise ValueError("Token and tool counts must be nonnegative integers")
    prices = [Decimal(str(x)) for x in (input_per_million, output_per_million, tool_price_usd)]
    if any(not p.is_finite() or p < 0 for p in prices):
        raise ValueError("Prices must be finite and nonnegative")
    amount = input_tokens * prices[0] + output_tokens * prices[1]
    amount += tool_calls * prices[2] * 1_000_000
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


class BudgetGuard:
    """Reserve worst-case charges atomically before network sends, across restarts.

    SQLite serializes concurrent reservations. Every retry needs a new attempt ID.
    Unknown charges are never released automatically: an interrupted
    request or absent usage may still be billable. This is a conservative ceiling,
    not an invoice. Completed usage can support an immutable settlement while preserving the original ceiling. Unknown historical spend blocks initialization. The caller
    must provide reconciled spend or a documented conservative upper bound.
    """

    def __init__(self, path, *, prior_total_microusd, prior_research_microusd, run_limits=None):
        # Explicit, documented approvals can change one run without resetting its spend.
        self.run_limits = dict(run_limits or {})
        for run, limit in self.run_limits.items():
            if (
                not isinstance(run, str)
                or not run
                or type(limit) is not int
                or not 0 < limit <= 50_000_000
            ):
                raise ValueError("Invalid approved run limit")
        for value in (prior_total_microusd, prior_research_microusd):
            if type(value) is not int or value < 0:
                raise ValueError("Reconcile prior spend before enabling paid requests")
        if not prior_research_microusd <= prior_total_microusd <= 50_000_000:
            raise ValueError("Invalid prior spend or project budget already exceeded")
        if prior_research_microusd > 10_000_000:
            raise ValueError("Research allowance already exceeded")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS opening (id INTEGER PRIMARY KEY, total INTEGER, research INTEGER)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, run TEXT, event TEXT, research INTEGER, amount INTEGER, request_hash TEXT, pricing_hash TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS settlements (id TEXT PRIMARY KEY, amount INTEGER, evidence TEXT)"
            )
            db.execute(
                "CREATE VIEW IF NOT EXISTS effective_reservations AS SELECT r.*, COALESCE(s.amount, r.amount) AS effective_amount FROM reservations r LEFT JOIN settlements s ON s.id=r.id"
            )
            row = db.execute("SELECT total, research FROM opening WHERE id=1").fetchone()
            expected = (prior_total_microusd, prior_research_microusd)
            if row is None:
                db.execute("INSERT INTO opening VALUES (1, ?, ?)", expected)
            elif row != expected:
                raise ValueError("Existing ledger opening balance cannot be changed")
        os.chmod(self.path, 0o600)

    @contextmanager
    def _connect(self):
        """Open a short-lived transactional connection; context managers commit or roll back."""
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(
        self,
        *,
        attempt_id,
        run_id,
        event_id,
        research,
        maximum_microusd,
        request_sha256,
        pricing_sha256,
    ):
        """Reserve within $50 total, $10 research and $1/event limits.

        Runs default to $5; a documented per-run approval may override that limit.
        The same ledger and run ID preserve all earlier spending.

        Event IDs are stable across retry/condition runs, so changing a run name
        cannot reset the event allowance. Duplicate attempt IDs are rejected;
        a crash after reservation consumes that reservation even before send.
        """
        if type(maximum_microusd) is not int or maximum_microusd <= 0:
            raise ValueError("A positive priced upper bound is required")
        if type(research) is not bool or not all(
            (attempt_id, run_id, event_id, request_sha256, pricing_sha256)
        ):
            raise ValueError("Reservation identity and research flag are required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            total, research_prior = db.execute(
                "SELECT total, research FROM opening WHERE id=1"
            ).fetchone()
            queries = [
                (
                    "SELECT COALESCE(SUM(effective_amount),0) FROM effective_reservations",
                    (),
                    total,
                    50_000_000,
                ),
                (
                    "SELECT COALESCE(SUM(effective_amount),0) FROM effective_reservations WHERE run=?",
                    (run_id,),
                    0,
                    self.run_limits.get(run_id, 5_000_000),
                ),
                (
                    "SELECT COALESCE(SUM(effective_amount),0) FROM effective_reservations WHERE event=?",
                    (event_id,),
                    0,
                    1_000_000,
                ),
            ]
            if research:
                queries.append(
                    (
                        "SELECT COALESCE(SUM(effective_amount),0) FROM effective_reservations WHERE research=1",
                        (),
                        research_prior,
                        10_000_000,
                    )
                )
            for query, params, prior, cap in queries:
                if prior + db.execute(query, params).fetchone()[0] + maximum_microusd > cap:
                    raise ValueError("Budget reservation would exceed a spending limit")
            db.execute(
                "INSERT INTO reservations VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt_id,
                    run_id,
                    event_id,
                    int(research),
                    maximum_microusd,
                    request_sha256,
                    pricing_sha256,
                ),
            )

    def settle(self, attempt_id, *, upper_microusd, evidence_sha256):
        """Replace an unused ceiling with an evidenced upper charge, retaining both.

        Call only for completed responses with complete usage and known prices.
        Missing usage, crashes and HTTP failures keep their full reservation.
        This is not an invoice refund. The evidence hash identifies the preserved
        provider response and dated price calculation. Settlements are immutable.
        """
        if type(upper_microusd) is not int or upper_microusd < 0 or not evidence_sha256:
            raise ValueError("Settlement needs a nonnegative upper charge and evidence")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT amount FROM reservations WHERE id=?", (attempt_id,)).fetchone()
            if row is None or upper_microusd > row[0]:
                raise ValueError("Settlement exceeds reservation or attempt is unknown")
            previous = db.execute(
                "SELECT amount, evidence FROM settlements WHERE id=?", (attempt_id,)
            ).fetchone()
            values = (upper_microusd, evidence_sha256)
            if previous is not None and previous != values:
                raise ValueError("Existing settlement cannot change")
            if previous is None:
                db.execute("INSERT INTO settlements VALUES (?, ?, ?)", (attempt_id, *values))


def audit_attempts(reports_dir):
    """Count physical attempt logs once, keeping absent usage and completions explicit.

    Cached predictions/report copies are used only to resolve model identities;
    their token totals are never added again. One request fingerprint can have
    many attempts, so retries are not collapsed. Legacy calls without start logs
    cannot be recovered by this audit and are listed as a scope limitation.
    """
    root = Path(reports_dir)
    identities = {}
    for path in root.rglob("*.json"):
        if "cost-audit" in path.parts:
            continue
        try:
            item = json.loads(path.read_text())
        except (ValueError, UnicodeError):
            continue
        if not isinstance(item, dict):
            continue
        fingerprint = item.get("request_sha256")
        payload = item.get("payload") or {}
        model = item.get("requested_model") or payload.get("model") or item.get("returned_model")
        if fingerprint and model:
            identities.setdefault(fingerprint, set()).add(model)
    records, totals = [], {}
    for start in sorted(root.rglob("*-started.json")):
        marker = json.loads(start.read_text())
        finish = start.with_name(start.name.replace("-started.json", "-finished.json"))
        result = json.loads(finish.read_text()) if finish.exists() else {}
        models = identities.get(marker.get("request_sha256"), set())
        model = (
            next(iter(models)) if len(models) == 1 else marker.get("requested_model", "unresolved")
        )
        scope = str(start.parent.relative_to(root))
        usage = result.get("usage") or {}
        known = all(
            type(usage.get(k)) is int and usage[k] >= 0
            for k in ("prompt_tokens", "completion_tokens")
        )
        record = {
            "start_log": str(start.relative_to(root)),
            "scope": scope,
            "model": model,
            "request_sha256": marker.get("request_sha256"),
            "completed": finish.exists(),
            "status": result.get("status", "interrupted_or_unknown"),
            "http_status": result.get("http_status"),
            "usage_known": known,
            "prompt_tokens": usage.get("prompt_tokens") if known else None,
            "completion_tokens": usage.get("completion_tokens") if known else None,
        }
        records.append(record)
        key = (scope, model)
        group = totals.setdefault(
            key,
            {
                "scope": scope,
                "model": model,
                "attempts": 0,
                "missing_usage": 0,
                "missing_completion": 0,
                "known_prompt_tokens": 0,
                "known_completion_tokens": 0,
                "statuses": Counter(),
                "http_429": 0,
            },
        )
        group["attempts"] += 1
        group["statuses"][record["status"]] += 1
        group["http_429"] += record["http_status"] == 429
        group["missing_completion"] += not finish.exists()
        group["missing_usage"] += not known
        if known:
            group["known_prompt_tokens"] += usage["prompt_tokens"]
            group["known_completion_tokens"] += usage["completion_tokens"]
    return {
        "version": "cost-audit-v1",
        "groups": list(totals.values()),
        "attempts": records,
        "actual_cost_usd": None,
        "remaining_budget_usd": None,
        "limitations": [
            "No invoices reconciled; free-tier claims are not verified charges",
            "Known tokens are a subtotal; missing usage is not zero",
            "Calls without attempt logs and use outside this repository are not covered",
            "Legacy attempt logs do not uniformly record endpoint or individual duration",
            "Cached replay totals are excluded to avoid double counting",
        ],
    }
