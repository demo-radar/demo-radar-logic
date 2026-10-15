"""Notebook HTTP, response validation and private caching; no model selection here."""

import json
import math
import os
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from demo_logic.notebook_support import save_private_json
from notebooks.tools.hashes import fingerprint


def parse_llm_tags(content, tags):
    """Return zero to two approved tags, rejecting malformed answers as failures."""
    obj = json.loads(content)
    if not isinstance(obj, dict) or set(obj) != {"tags"}:
        raise ValueError("Expected exactly one tags field")
    result = obj["tags"]
    if (
        not isinstance(result, list)
        or len(result) > 2
        or any(not isinstance(t, str) or t not in tags for t in result)
        or len(set(result)) != len(result)
    ):
        raise ValueError("Expected up to two distinct approved tags")
    return result


def retry_delay(header, attempt):
    """Respect Retry-After seconds or an HTTP date; otherwise use bounded backoff."""
    try:
        seconds = float(header)
        if not math.isfinite(seconds):
            raise ValueError("Non-finite retry delay")
        return max(0, seconds)
    except (TypeError, ValueError):
        try:
            return max(0, (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 2 ** (attempt + 1) + random.random()


def chat_request(
    config,
    payload,
    *,
    tags,
    cache_dir,
    allow_live=False,
    api_key=None,
    max_retry_wait_seconds=120,
    request_timeout_seconds=60,
    progress=print,
    opener=urlopen,
    sleep=time.sleep,
    clock=time.monotonic,
    content_parser=parse_llm_tags,
):
    """Fetch one chat completion, or replay its exact private cached response.

    Args:
        config: HTTPS endpoint, model and environment-variable name for the key.
        payload: Complete request containing the title and public prompt only.
        tags: Approved output vocabulary.
        content_parser: Validator returning tags from response text; default tags-only JSON.
            Experiments using richer output must supply the same parser on replay.
        cache_dir: Ignored private directory. Change it to deliberately refresh a run.
        allow_live: False permits cached responses only, never a network request.
        api_key: Optional private key supplied by the notebook config loader.
            Falls back to the named process variable; never written to reports.
        max_retry_wait_seconds: Maximum wait per retry (0–240); longer waits pause.
        request_timeout_seconds: Per-attempt timeout, from 1 to 240 seconds.
            Browser research may need more time than ordinary classification.
        progress: Receives plain progress messages without titles or credentials.
        opener, sleep, clock: Injectable I/O for tests without provider calls.

    Returns:
        Prediction, usage, original latency, response identity and attempt history.
        Missing cache and failed calls have distinct statuses. Failures are never
        cached as successes. Authentication/configuration/quota errors stop the batch.
        Logs omit keys, headers and server error bodies. At most three attempts fit
        within five minutes; waits above the configured limit pause for a later rerun.
    """
    if type(max_retry_wait_seconds) is not int or not 0 <= max_retry_wait_seconds <= 240:
        raise ValueError("Retry wait limit must be an integer from 0 to 240")
    if type(request_timeout_seconds) is not int or not 1 <= request_timeout_seconds <= 240:
        raise ValueError("Request timeout must be an integer from 1 to 240")
    needs_search = any(t.get("type") == "browser_search" for t in payload.get("tools", []))
    identity = fingerprint({"endpoint": config["endpoint"], "payload": payload})
    path = cache_dir / f"{identity}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if saved.get("request_sha256") != identity:
            raise ValueError("Cached request identity does not match")
        if needs_search:
            from notebooks.tools.research import research_evidence

            research_evidence(saved["response"])
        predicted = content_parser(saved["response"]["choices"][0]["message"]["content"], tags)
        return {**saved, "predicted": predicted, "cached": True}
    failure_dir = cache_dir.parent / "hosted-failures" / identity
    failures = sorted(failure_dir.glob("*.json"))
    if not allow_live and failures:
        saved = json.loads(failures[-1].read_text())
        if saved.get("request_sha256") != identity:
            raise ValueError("Saved failure identity does not match")
        return {**saved, "cached": True}
    result = {
        "request_sha256": identity,
        "payload": payload,
        "requested_model": config["model"],
        "status": "not_run",
        "predicted": [],
        "cached": False,
        "attempts": [],
        "duration_seconds": None,
        "usage": {},
        "stop_batch": False,
    }
    if not allow_live:
        return result
    key = api_key or os.environ.get(config["key_env"])
    if not key:
        raise ValueError(f"Set {config['key_env']} in the notebook kernel first")
    if not config["endpoint"].startswith("https://"):
        raise ValueError("Provider endpoint must use HTTPS")
    started = clock()
    for attempt in range(3):
        attempt_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        log_dir = cache_dir.parent / "hosted-attempts"
        marker = {
            "request_sha256": identity,
            "attempt": attempt + 1,
            "started_at": attempt_id,
            "status": "started",
        }
        save_private_json(log_dir / f"{attempt_id}-started.json", marker)
        # A start without a completion means interrupted/unknown, not free success.
        entry = {"attempt": attempt + 1, "started_at": attempt_id}
        should_retry = False
        delay = 0
        try:
            request = Request(
                config["endpoint"],
                json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "User-Agent": "DemoLogic/0.1",
                    "Accept": "application/json",
                },
            )
            with opener(
                request, timeout=min(request_timeout_seconds, max(1, 300 - (clock() - started)))
            ) as response:
                body = json.loads(response.read())
            if isinstance(body, dict):
                result.update(response=body, usage=body.get("usage", {}))
                entry["usage"] = body.get("usage", {})
            if not isinstance(body.get("model"), str) or not body["model"]:
                raise ValueError("Missing returned model identity")
            if body["choices"][0].get("finish_reason") != "stop":
                raise ValueError("Response is incomplete")
            if needs_search:
                from notebooks.tools.research import research_evidence

                research_evidence(body)
            result.update(
                predicted=content_parser(body["choices"][0]["message"]["content"], tags),
                response=body,
                returned_model=body["model"],
                usage=body.get("usage", {}),
                status="ok",
            )
            entry.update(status="ok", usage=body.get("usage", {}))
        except HTTPError as exc:
            entry.update(status="http_error", http_status=exc.code)
            result.update(status="failed", error=f"HTTP {exc.code}")
            should_retry = exc.code == 429 or 500 <= exc.code <= 599
            delay = retry_delay(exc.headers.get("Retry-After"), attempt)
            entry["retry_after_seconds"] = delay
            result["stop_batch"] = exc.code in {400, 401, 403, 404, 429}
        except (URLError, TimeoutError, OSError):
            entry.update(status="network_error")
            result.update(status="failed", error="Network error or timeout")
            should_retry = True
            delay = retry_delay(None, attempt)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            entry.update(status="invalid_response")
            result.update(status="failed", error="Invalid or incomplete model response")
        result["attempts"].append(entry)
        save_private_json(log_dir / f"{attempt_id}-finished.json", entry)
        result["duration_seconds"] = clock() - started
        if result["status"] == "ok":
            result["stop_batch"] = False
            save_private_json(path, result)
            return result
        if (
            not should_retry
            or attempt == 2
            or delay > max_retry_wait_seconds
            or clock() - started + delay >= 300
        ):
            if should_retry:
                result["stop_batch"] = True
            if result["stop_batch"]:
                progress(
                    f"{config['model']}: paused ({result['error']}). "
                    "Completed answers are saved; rerun later to resume."
                )
            break
        remaining = delay
        while remaining > 0:
            progress(
                f"{config['model']}: {result['error']}; waiting {remaining:.0f}s "
                f"before attempt {attempt + 2}/3. Completed answers are saved."
            )
            chunk = min(30, remaining)
            sleep(chunk)
            remaining -= chunk
    save_private_json(failure_dir / f"{attempt_id}.json", result)
    return result


def load_hosted_inputs(root):
    """Verify the private snapshot and return validation representatives in saved order.

    Reuse the locked benchmark and DR-40 selection. Final-review membership is
    verified by the common loader, but its reference labels are never returned.
    The notebook, not this helper, chooses the screening/check split and prompts.
    """
    from demo_logic.benchmark import _csv, load_benchmark, representative_selection
    from demo_logic.evaluation import parse_review_tags
    from demo_logic.snapshot import load_snapshot
    from demo_logic.taxonomy import topic_tags

    rows, source = load_snapshot(root / "data/dataset.jsonl", root / "data/manifest.json")
    bundle = load_benchmark(root / "data/benchmark", rows, source["content_sha256"])
    if bundle.manifest.get("status") != "frozen" or source["taxonomy_version"] != "v2":
        raise ValueError("Notebook 07 requires locked split membership and taxonomy v2")

    by_id = {row["external_id"]: row for row in rows}
    selection = representative_selection(bundle)
    selected_ids = {item["external_id"] for item in selection["records"]}
    validation = [
        {**by_id[a["external_id"]], "group_id": a["group_id"]}
        for a in bundle.manifest["assignments"]
        if a["split"] == "validation" and a["external_id"] in selected_ids
    ]
    assert set(bundle.pilot_ids).issubset({row["external_id"] for row in validation})
    tags = sorted(topic_tags(source["taxonomy_version"]))
    reviewed_pilot = {
        row["external_id"]: parse_review_tags(row["reviewed_tags"], set(tags))
        for row in _csv(bundle.paths["rubric_pilot"], {"external_id", "reviewed_tags"})
    }
    if len(reviewed_pilot) != 40:
        raise ValueError("The 40-record development pilot must be complete")

    return validation, tags, reviewed_pilot, source, selection
