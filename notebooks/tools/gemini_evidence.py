"""Budgeted Gemini evidence collection and model comparison transport."""

import json
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from demo_logic.notebook_support import save_private_json
from notebooks.tools.costs import cost_microusd
from notebooks.tools.gemini import ENDPOINT, decode_result
from notebooks.tools.hashes import fingerprint
from notebooks.tools.hosted import parse_llm_tags, retry_delay

PRICES = {
    "gemini-2.5-flash": (".30", "2.50"),
    "gemini-3.8-flash": (".75", "3.75"),
    "gemini-3.5-flash-lite": (".30", "2.50"),
}
PRICE_DATE = "2026-10-02"
PRICE_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"


def evidence_from(body):
    """Require a completed answer, real search queries and provider citations.

    A source link is provenance, not proof of an exact event/date match. Preserve
    the original response for inspection; never execute returned HTML or text.
    """
    if body.get("status") != "completed":
        raise ValueError("Incomplete research response")
    steps = body.get("steps", [])
    blocks = [
        c
        for s in steps
        if s.get("type") == "model_output"
        for c in s.get("content", [])
        if c.get("type") == "text"
    ]
    queries = [
        q
        for s in steps
        if s.get("type") == "google_search_call"
        for q in s.get("arguments", {}).get("queries", [])
    ]
    citations = [
        a
        for c in blocks
        for a in c.get("annotations", [])
        if a.get("type") == "url_citation" and a.get("url", "").startswith("https://")
    ]
    text = "\n".join(c.get("text", "") for c in blocks).strip()
    if not text or not queries or not citations:
        raise ValueError("Research requires actual search traces and citations")
    return {"text": text, "queries": queries, "citations": citations, "exact_event_verified": False}


def usage_upper(body, model, *, research=False):
    """Gross USD-millionth upper estimate; no discounts/free allowances assumed.

    Price every reported token at the higher output rate, including thought/tool
    tokens, and add the full 2.5 grounded-prompt fee for research. Deliberately
    conservative: this is not the user's invoice. Unknown usage returns None.
    """
    usage = body.get("usage") or {}
    total = usage.get("total_tokens")
    if type(total) is not int or total < 0 or body.get("status") != "completed":
        return None
    if research and model != "gemini-2.5-flash":
        raise ValueError("Only 2.5 research pricing is implemented")
    return cost_microusd(0, total, *PRICES[model], tool_calls=int(research), tool_price_usd=".035")


def request(
    payload,
    *,
    event_id,
    folder,
    guard,
    key,
    tags,
    research=False,
    live=False,
    run_id="gemini-required-evidence-v1",
    research_budget=True,
    content_parser=parse_llm_tags,
):
    """Replay or perform one reserved HTTP attempt with private audit and cooldown.

    Only the three priced models are accepted. Research is limited to 2.5 Flash;
    judges have no tools and consume the same frozen evidence. Every physical
    request has its own reservation. Complete usage settles the unused ceiling;
    unsuccessful/unknown requests retain theirs. No automatic retries.
    A caller can supply a separate run ID and classify title-only calls outside
    the research allowance; actual research always consumes that allowance.
    content_parser validates response text; use the same parser for live and replay.
    """
    model = payload.get("model")
    if model not in PRICES or (research and model != "gemini-2.5-flash"):
        raise ValueError("Unpriced model or research setup")
    expected_tools = [{"type": "google_search"}] if research else []
    if payload.get("tools", []) != expected_tools:
        raise ValueError("Unexpected tools")
    identity = fingerprint({"endpoint": ENDPOINT, "payload": payload})
    folder = Path(folder)
    path = folder / "cache" / (identity + ".json")
    if path.exists():
        result = json.loads(path.read_text())
        if result["request_sha256"] != identity:
            raise ValueError("Cache identity mismatch")
        if not research and result.get("status") == "ok" and "response" in result:
            result.update(decode_result(result["response"], tags, content_parser=content_parser))
        return {**result, "cached": True}
    if not live:
        return {"status": "missing_cache", "predicted": [], "cached": False}
    cooldown = folder / (model + "-cooldown.json")
    if cooldown.exists() and json.loads(cooldown.read_text())["retry_at_epoch"] > time.time():
        return {"status": "rate_limit_paused", "predicted": [], "cached": False}
    if not key:
        raise ValueError("GEMINI_API_KEY missing")
    output = payload["generation_config"]["max_output_tokens"]
    if type(output) is not int or not 1 <= output <= 4096:
        raise ValueError("Output limit must be 1 to 4096")
    maximum = cost_microusd(
        1048576 if research else len(json.dumps(payload).encode()) + 2048,
        output,
        *PRICES[model],
        tool_calls=int(research),
        tool_price_usd=".035",
    )
    attempt = str(uuid.uuid4())
    pricing = {
        "date": PRICE_DATE,
        "source": PRICE_SOURCE,
        "model": model,
        "input_output_per_million": PRICES[model],
        "research_prompt_usd": ".035" if research else "0",
    }
    guard.reserve(
        attempt_id=attempt,
        run_id=run_id,
        event_id=event_id,
        research=research_budget or research,
        maximum_microusd=maximum,
        request_sha256=identity,
        pricing_sha256=fingerprint(pricing),
    )
    result = {
        "attempt_id": attempt,
        "request_sha256": identity,
        "requested_model": model,
        "payload": payload,
        "pricing": pricing,
        "maximum_microusd": maximum,
        "external_id": event_id,
        "research": research,
    }
    save_private_json(folder / "attempts" / (attempt + "-started.json"), result)
    start = time.perf_counter()
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
        result.update(response=body, usage=body.get("usage"), status="ok")
        try:
            if research:
                result["evidence"] = evidence_from(body)
            else:
                result.update(decode_result(body, tags, content_parser=content_parser))
        except (ValueError, KeyError, TypeError):
            result.update(
                status="invalid_evidence" if research else "invalid_response", predicted=[]
            )
        upper = usage_upper(body, model, research=research)
        if upper is not None:
            upper = min(upper, maximum)  # Keep the tighter of two conservative bounds.
        result["gross_upper_microusd"] = upper
        result.update(duration_seconds=time.perf_counter() - start, cached=False)
        save_private_json(folder / "attempts" / (attempt + "-finished.json"), result)
        save_private_json(path, result)
        if upper is not None:
            guard.settle(
                attempt,
                upper_microusd=upper,
                evidence_sha256=fingerprint({"response": body, "pricing": pricing}),
            )
    except HTTPError as error:
        try:
            detail = json.loads(error.read()).get("error", {})
        except ValueError:
            detail = {}
        result.update(
            status="http_error",
            http_status=error.code,
            error_message=str(detail.get("message", "")).replace(key, "[redacted]"),
            retry_after=error.headers.get("Retry-After"),
            predicted=[],
        )
        if error.code == 429 and result["retry_after"]:
            cooldown.parent.mkdir(parents=True, exist_ok=True)
            cooldown.write_text(
                json.dumps({"retry_at_epoch": time.time() + retry_delay(result["retry_after"], 0)})
            )
            cooldown.chmod(0o600)
    except (URLError, TimeoutError, OSError):
        result.update(status="network_error", predicted=[])
    if "duration_seconds" not in result:
        result.update(duration_seconds=time.perf_counter() - start, cached=False)
    save_private_json(folder / "attempts" / (attempt + "-finished.json"), result)
    if "response" in result:
        save_private_json(path, result)
    return result
