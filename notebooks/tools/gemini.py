"""Gemini transport and provenance helpers for the bounded notebook experiment."""

import json
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from demo_logic.notebook_support import save_private_json
from notebooks.tools.costs import cost_microusd
from notebooks.tools.hashes import fingerprint
from notebooks.tools.hosted import parse_llm_tags

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
PRICING = {
    "date": "2026-10-02",
    "model": "gemini-2.5-flash",
    "input_per_million": ".30",
    "output_per_million": "2.50",
    "grounded_prompt_usd": ".035",
    "source": "https://ai.google.dev/gemini-api/docs/pricing",
}


def decode_result(body, tags, *, content_parser=parse_llm_tags):
    """Validate tags and retain provider search traces, independently of model claims.

    Strip only an optional JSON code fence. Do not repair labels or invent missing
    sources. Search execution does not establish that a source matches the event.
    content_parser defaults to the approved two-tag validator. A versioned
    experiment may supply a stricter validator for its own response contract.
    """
    if body.get("status") != "completed":
        raise ValueError("Gemini response is not complete")
    steps = body.get("steps", [])
    blocks = [
        c
        for s in steps
        if s.get("type") == "model_output"
        for c in s.get("content", [])
        if c.get("type") == "text"
    ]
    text = "\n".join(c.get("text", "") for c in blocks).strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    queries = [
        q
        for s in steps
        if s.get("type") == "google_search_call"
        for q in s.get("arguments", {}).get("queries", [])
    ]
    citations = [
        a for c in blocks for a in c.get("annotations", []) if a.get("type") == "url_citation"
    ]
    return {
        "predicted": content_parser(text, tags),
        "search_executed": bool(queries),
        "queries": queries,
        "citations": citations,
    }


def gemini_request(payload, *, event_id, tags, folder, key, guard, live=False):
    """Replay an exact response or send one budget-reserved Gemini request.

    One HTTP attempt per invocation; no hidden retries. Completed invalid JSON is
    retained as a failed prediction, not silently repaired or repeatedly sampled.
    HTTP errors remain resumable. Credentials and headers are never persisted.
    Search calls reserve the full model input-window ceiling plus grounding fee;
    ordinary calls reserve a conservative prompt-byte bound. Reservations remain
    even on failure, and the shared ledger stops calls at the spending limits.
    """
    if payload.get("model") != PRICING["model"]:
        raise ValueError(
            "This adapter is priced for Gemini 2.5 Flash only; price a separate experiment before changing models"
        )
    identity = fingerprint({"endpoint": ENDPOINT, "payload": payload})
    path = folder / "cache" / (identity + ".json")
    if path.exists():
        saved = json.loads(path.read_text())
        if saved["request_sha256"] != identity:
            raise ValueError("Cache identity mismatch")
        return {**saved, "cached": True}
    if not live:
        return {"status": "missing_cache", "predicted": [], "cached": False}
    cooldown_path = folder / "cooldown.json"
    if cooldown_path.exists():
        cooldown = json.loads(cooldown_path.read_text())
        if time.time() < cooldown["retry_at_epoch"]:
            return {
                "status": "rate_limit_paused",
                "predicted": [],
                "cached": False,
                "retry_at_epoch": cooldown["retry_at_epoch"],
            }
    if not key:
        raise ValueError("GEMINI_API_KEY is missing")
    search = bool(payload.get("tools"))
    input_bound = 1048576 if search else len(json.dumps(payload).encode()) + 2048
    maximum = cost_microusd(
        input_bound,
        payload["generation_config"]["max_output_tokens"],
        ".30",
        "2.50",
        tool_calls=int(search),
        tool_price_usd=".035",
    )
    attempt = str(uuid.uuid4())
    guard.reserve(
        attempt_id=attempt,
        run_id="gemini-comparison-v1",
        event_id=event_id,
        research=True,
        maximum_microusd=maximum,
        request_sha256=identity,
        pricing_sha256=fingerprint(PRICING),
    )
    record = {
        "request_sha256": identity,
        "requested_model": payload["model"],
        "payload": payload,
        "pricing": PRICING,
        "maximum_microusd": maximum,
        "external_id": event_id,
    }
    save_private_json(folder / "attempts" / (attempt + "-started.json"), record)
    start = time.perf_counter()
    try:
        request = Request(
            ENDPOINT,
            json.dumps(payload).encode(),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=120) as response:
            body = json.loads(response.read())
        record.update(response=body, usage=body.get("usage"), status="ok")
        try:
            record.update(decode_result(body, tags))
        except (ValueError, KeyError, TypeError):
            record.update(status="invalid_response", predicted=[])
    except HTTPError as error:
        try:
            detail = json.loads(error.read()).get("error", {})
        except ValueError:
            detail = {}
        record.update(
            status="http_error",
            http_status=error.code,
            predicted=[],
            error_code=detail.get("code"),
            error_status=detail.get("status"),
            error_message=str(detail.get("message", "")).replace(key, "[redacted]"),
            retry_after=error.headers.get("Retry-After"),
        )
    except (URLError, TimeoutError, OSError):
        record.update(status="network_error", predicted=[])
    record.update(duration_seconds=time.perf_counter() - start, cached=False)
    save_private_json(folder / "attempts" / (attempt + "-finished.json"), record)
    if record.get("http_status") == 429 and record.get("retry_after"):
        from notebooks.tools.hosted import retry_delay

        cooldown_path.write_text(
            json.dumps({"retry_at_epoch": time.time() + retry_delay(record["retry_after"], 0)})
        )
        cooldown_path.chmod(0o600)
    if "response" in record:
        save_private_json(path, record)
    return record
