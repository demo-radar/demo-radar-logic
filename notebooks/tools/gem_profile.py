"""Gem-format validation and audited native-search transport for Notebook 15.

Model prompts and comparisons stay in the notebook. Native search query counts
are provider managed: reservations are allowances, not a provider-enforced cap.
Reconcile complete usage before another request; stop on unknown usage/overruns.
"""

import json
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from demo_logic.notebook_support import save_private_json
from notebooks.tools.costs import cost_microusd
from notebooks.tools.gemini import ENDPOINT
from notebooks.tools.hashes import fingerprint
from notebooks.tools.hosted import parse_llm_tags, retry_delay

PRICING = {
    "model": "gemini-3.8-flash",
    "input": ".75",
    "output": "3.75",
    "query": ".014",
    "date": "2026-10-03",
    "source": "https://ai.google.dev/gemini-api/docs/pricing",
}


def decode_gem(body, tags):
    """Read the Gem's first JSON object and keep its reason/review metadata.

    Optional Markdown fences and trailing explanation are presentation only.
    Never repair tag slugs or trim excess tags. Confidence is a self-report,
    not a calibrated probability, and does not determine evaluation labels.
    """
    if body.get("status") != "completed":
        raise ValueError("Incomplete response")
    blocks = [
        c
        for s in body.get("steps", [])
        if s.get("type") == "model_output"
        for c in s.get("content", [])
        if c.get("type") == "text"
    ]
    text = "\n".join(c.get("text", "") for c in blocks).strip()
    if text.startswith("```json"):
        text = text[7:].lstrip()
    elif text.startswith("```"):
        text = text[3:].lstrip()
    obj, _ = json.JSONDecoder().raw_decode(text)
    if not isinstance(obj, dict) or set(obj) != {
        "tags",
        "confidence",
        "reason",
        "needs_review",
        "proposals",
    }:
        raise ValueError("Unexpected Gem fields")
    predicted = parse_llm_tags(json.dumps({"tags": obj["tags"]}), tags)
    confidence = obj["confidence"]
    if type(confidence) not in {int, float} or not 0 <= confidence <= 1:
        raise ValueError("Invalid confidence")
    if (
        not isinstance(obj["reason"], str)
        or type(obj["needs_review"]) is not bool
        or not isinstance(obj["proposals"], list)
    ):
        raise ValueError("Invalid Gem metadata")
    if not predicted and not obj["needs_review"]:
        raise ValueError("Empty tags require review")
    return {"predicted": predicted, "gem": obj}


def search_trace(body):
    """Return provider search queries and citations, independent of model claims."""
    steps = body.get("steps", [])
    queries = [
        q
        for s in steps
        if s.get("type") == "google_search_call"
        for q in s.get("arguments", {}).get("queries", [])
    ]
    citations = [
        a
        for s in steps
        if s.get("type") == "model_output"
        for c in s.get("content", [])
        if c.get("type") == "text"
        for a in c.get("annotations", [])
        if a.get("type") == "url_citation"
    ]
    return {"queries": queries, "citations": citations, "search_executed": bool(queries)}


def usage_cost(body, search):
    """Conservative post-response USD estimate, including all tokens and queries.

    Charge every token at the output rate and every reported search query at
    full price. Ignore discounts/free allowances. Never infer zero from missing
    usage; query traces and billed-tool counts are both inspected.
    """
    usage = body.get("usage") or {}
    total = usage.get("total_tokens")
    if type(total) is not int or total < 0:
        return None
    counts = usage.get("grounding_tool_count", [])
    if not isinstance(counts, list):
        return None
    reported = 0
    for row in counts:
        if row.get("type") == "google_search":
            n = row.get("count")
            if type(n) is not int or n < 0:
                return None
            reported += n
    queries = max(len(search_trace(body)["queries"]), reported) if search else 0
    return cost_microusd(
        0,
        total,
        PRICING["input"],
        PRICING["output"],
        tool_calls=queries,
        tool_price_usd=PRICING["query"],
    )


def gem_request(
    payload,
    *,
    event_id,
    folder,
    key,
    tags,
    guard,
    live=False,
    decoder=decode_gem,
    run_id="gem-adaptation-v1",
    research_budget=True,
):
    """Cache a single request, preserving failures and reconciling actual usage.

    Before search requests reserve 32K input tokens, the output cap and eight
    search queries. This is an operational allowance, not a hard billing bound.
    The provider controls native search. After a response, settle a conservative
    usage estimate or reserve any extra amount before continuing. If accounting
    cannot be reconciled, persist a stop marker and make no further live calls.
    There are no automatic retries and no sampling again after invalid output.
    ``decoder`` validates both live and cached responses. ``run_id`` separates
    experiment accounting without resetting project or per-event totals.
    ``research_budget`` charges non-search diagnostics to the research allowance;
    native search always uses that allowance regardless of this option.
    """
    if payload.get("model") != PRICING["model"]:
        raise ValueError("Unpriced model")
    search = payload.get("tools", []) == [{"type": "google_search"}]
    if payload.get("tools", []) not in ([], [{"type": "google_search"}]):
        raise ValueError("Unsupported tool")
    output = payload["generation_config"]["max_output_tokens"]
    if type(output) is not int or not 1 <= output <= 4096:
        raise ValueError("Unsupported output limit")
    folder = Path(folder)
    identity = fingerprint({"endpoint": ENDPOINT, "payload": payload})
    cache = folder / "cache" / (identity + ".json")
    if cache.exists():
        result = json.loads(cache.read_text())
        if result["request_sha256"] != identity:
            raise ValueError("Cache mismatch")
        if result.get("status") == "ok":
            result.update(decoder(result["response"], tags))
        return {**result, "cached": True}
    if not live:
        return {"status": "missing_cache", "predicted": [], "cached": False}
    block = folder / "accounting-stop.json"
    if block.exists():
        raise ValueError("Reconcile the recorded cost before resuming live requests")
    cooldown = folder / "cooldown.json"
    if cooldown.exists() and json.loads(cooldown.read_text())["retry_at_epoch"] > time.time():
        return {"status": "rate_limit_paused", "predicted": [], "cached": False}
    # A started request without a finish may have incurred costs; do not lose it.
    for started in (folder / "attempts").glob("*-started.json"):
        if not started.with_name(started.name.replace("-started.json", "-finished.json")).exists():
            raise ValueError("An interrupted request needs cost reconciliation")
    if not key:
        raise ValueError("GEMINI_API_KEY missing")
    amount = cost_microusd(
        max(32768 if search else 0, len(json.dumps(payload).encode()) + 2048),
        output,
        PRICING["input"],
        PRICING["output"],
        tool_calls=8 if search else 0,
        tool_price_usd=PRICING["query"],
    )
    attempt = str(uuid.uuid4())
    reserve_args = {
        "run_id": run_id,
        "event_id": event_id,
        "research": research_budget or search,
        "request_sha256": identity,
        "pricing_sha256": fingerprint(PRICING),
    }
    try:
        guard.reserve(attempt_id=attempt, maximum_microusd=amount, **reserve_args)
    except ValueError as exc:
        if str(exc) != "Budget reservation would exceed a spending limit":
            raise
        return {
            "status": "budget_paused",
            "predicted": [],
            "cached": False,
            "reservation_microusd": amount,
        }
    record = {
        "attempt_id": attempt,
        "external_id": event_id,
        "request_sha256": identity,
        "payload": payload,
        "pricing": PRICING,
        "search_enabled": search,
        "reservation_microusd": amount,
        "predicted": [],
    }
    save_private_json(folder / "attempts" / (attempt + "-started.json"), record)
    start = time.perf_counter()
    body = None
    try:
        with urlopen(
            Request(
                ENDPOINT,
                json.dumps(payload).encode(),
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            ),
            timeout=120,
        ) as response:
            body = json.loads(response.read())
        record.update(response=body, usage=body.get("usage"), **search_trace(body))
        try:
            record.update(decoder(body, tags), status="ok")
        except (ValueError, KeyError, TypeError):
            record.update(status="invalid_response", predicted=[])
    except HTTPError as exc:
        record.update(
            status="http_error", http_status=exc.code, retry_after=exc.headers.get("Retry-After")
        )
        if exc.code == 429:
            save_private_json(
                cooldown,
                {"retry_at_epoch": time.time() + retry_delay(exc.headers.get("Retry-After"), 0)},
            )
    except (URLError, TimeoutError, OSError, ValueError):
        record.update(status="network_or_decode_error")
    record.update(duration_seconds=time.perf_counter() - start, cached=False)
    cost = usage_cost(body, search) if body is not None else None
    record["gross_upper_microusd"] = cost
    # Persist provider output before ledger settlement so no completed answer is lost.
    finish = folder / "attempts" / (attempt + "-finished.json")
    save_private_json(folder / "attempts" / (attempt + "-response.json"), record)
    if cost is None:
        save_private_json(
            block,
            {"attempt_id": attempt, "reason": "Missing usage; reservation is not a verified bill"},
        )
        record["accounting_pending"] = True
    else:
        try:
            if cost > amount:
                guard.reserve(
                    attempt_id=attempt + "-usage-extra",
                    maximum_microusd=cost - amount,
                    **reserve_args,
                )
            else:
                guard.settle(
                    attempt,
                    upper_microusd=cost,
                    evidence_sha256=fingerprint({"response": body, "pricing": PRICING}),
                )
        except ValueError:
            save_private_json(
                block,
                {
                    "attempt_id": attempt,
                    "reason": "Usage estimate exceeds available reservation/budget",
                    "usage_microusd": cost,
                },
            )
            record["accounting_pending"] = True
    save_private_json(finish, record)
    if body is not None:
        save_private_json(cache, record)
    return record
