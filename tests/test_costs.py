"""Budget safety and legacy attempt accounting, without network requests."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from notebooks.tools.costs import BudgetGuard, audit_attempts, cost_microusd


def reserve(guard, attempt, amount=100_000, **changes):
    args = {
        "attempt_id": attempt,
        "run_id": "run",
        "event_id": "event",
        "research": False,
        "maximum_microusd": amount,
        "request_sha256": "request",
        "pricing_sha256": "price",
    }
    args.update(changes)
    guard.reserve(**args)


def test_price_includes_output_and_tools():
    assert cost_microusd(2000, 1000, ".75", "4.5", tool_calls=2, tool_price_usd=".01") == 26_000
    with pytest.raises(ValueError):
        cost_microusd(2, 1, "NaN", "1")


def test_unknown_prior_spend_blocks(tmp_path):
    with pytest.raises(ValueError):
        BudgetGuard(tmp_path / "budget.db", prior_total_microusd=None, prior_research_microusd=0)


def test_restart_duplicate_and_event_cap(tmp_path):
    args = {"prior_total_microusd": 0, "prior_research_microusd": 0}
    g = BudgetGuard(tmp_path / "budget.db", **args)
    reserve(g, "first", 600_000)
    again = BudgetGuard(tmp_path / "budget.db", **args)
    with pytest.raises(sqlite3.IntegrityError):
        reserve(again, "first", 100_000)
    with pytest.raises(ValueError):
        reserve(again, "second", 500_000, run_id="new-run")
    reserve(again, "third", 400_000)
    with pytest.raises(ValueError):
        BudgetGuard(tmp_path / "budget.db", prior_total_microusd=1, prior_research_microusd=0)


def test_research_and_total_caps(tmp_path):
    g = BudgetGuard(
        tmp_path / "a.db", prior_total_microusd=49_900_000, prior_research_microusd=9_900_000
    )
    reserve(g, "a", 100_000, research=True)
    with pytest.raises(ValueError):
        reserve(g, "b", 1, event_id="other")
    g = BudgetGuard(
        tmp_path / "b.db", prior_total_microusd=10_000_000, prior_research_microusd=10_000_000
    )
    with pytest.raises(ValueError):
        reserve(g, "a", 1, research=True)


def test_concurrent_reservations_cannot_overspend(tmp_path):
    g = BudgetGuard(tmp_path / "a.db", prior_total_microusd=49_000_000, prior_research_microusd=0)

    def attempt(i):
        try:
            reserve(g, str(i), 600_000, event_id=str(i))
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sum(pool.map(attempt, range(2))) == 1


def test_run_cap(tmp_path):
    g = BudgetGuard(tmp_path / "a.db", prior_total_microusd=0, prior_research_microusd=0)
    for i in range(5):
        reserve(g, str(i), 1_000_000, event_id=str(i))
    with pytest.raises(ValueError):
        reserve(g, "six", 1, event_id="six")


def test_attempt_audit_does_not_count_cached_usage_twice(tmp_path):
    def save(name, value):
        (tmp_path / name).write_text(json.dumps(value))

    save(
        "cache.json",
        {"request_sha256": "hash", "requested_model": "model", "usage": {"prompt_tokens": 99}},
    )
    save("1-started.json", {"request_sha256": "hash"})
    save(
        "1-finished.json", {"status": "ok", "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
    )
    save("2-started.json", {"request_sha256": "hash"})
    save("2-finished.json", {"status": "http_error", "http_status": 429})
    save("3-started.json", {"request_sha256": "hash"})
    r = audit_attempts(tmp_path)
    g = r["groups"][0]
    assert g["attempts"] == 3 and g["missing_usage"] == 2 and g["missing_completion"] == 1
    assert g["known_prompt_tokens"] == 10 and g["known_completion_tokens"] == 2
    assert g["http_429"] == 1 and r["actual_cost_usd"] is None


def test_settlement_preserves_ceiling_and_releases_only_evidenced_difference(tmp_path):
    g = BudgetGuard(tmp_path / "a.db", prior_total_microusd=0, prior_research_microusd=0)
    reserve(g, "one", 900_000)
    g.settle("one", upper_microusd=100_000, evidence_sha256="evidence")
    g.settle("one", upper_microusd=100_000, evidence_sha256="evidence")
    reserve(g, "two", 900_000)
    with pytest.raises(ValueError):
        reserve(g, "three", 1)
    with pytest.raises(ValueError):
        g.settle("one", upper_microusd=0, evidence_sha256="different")
    with pytest.raises(ValueError):
        g.settle("unknown", upper_microusd=0, evidence_sha256="evidence")
    with sqlite3.connect(g.path) as db:
        assert db.execute("SELECT amount FROM reservations WHERE id='one'").fetchone()[0] == 900_000


def test_settlement_cannot_increase_reserved_charge(tmp_path):
    g = BudgetGuard(tmp_path / "a.db", prior_total_microusd=0, prior_research_microusd=0)
    reserve(g, "one", 10)
    with pytest.raises(ValueError):
        g.settle("one", upper_microusd=11, evidence_sha256="evidence")


def test_approved_run_limit_preserves_existing_spend_and_other_limits(tmp_path):
    args = {"prior_total_microusd": 0, "prior_research_microusd": 0}
    g = BudgetGuard(tmp_path / "a.db", **args)
    for i in range(5):
        reserve(g, str(i), 1_000_000, event_id=str(i))
    with pytest.raises(ValueError):
        reserve(g, "blocked", 1, event_id="new")
    approved = BudgetGuard(g.path, **args, run_limits={"run": 5_250_000})
    reserve(approved, "approved", 250_000, event_id="new")
    with pytest.raises(ValueError):
        reserve(approved, "over", 1, event_id="another")
    with pytest.raises(ValueError):
        reserve(approved, "event-over", 1, run_id="other", event_id="0")
    research_full = BudgetGuard(
        tmp_path / "b.db",
        prior_total_microusd=10_000_000,
        prior_research_microusd=10_000_000,
        run_limits={"run": 5_250_000},
    )
    with pytest.raises(ValueError):
        reserve(research_full, "research-over", 1, research=True)
