"""Validate browser-search provenance for notebook comparisons."""


def research_evidence(body):
    """Extract prose and source URLs only when the response proves search ran.

    Search results are provenance, not proof that the answer is correct. Preserve
    the full provider response separately so a reviewer can inspect tool outputs.
    A model's unsupported claim that it searched is rejected.
    """
    choice = body["choices"][0]
    message = choice["message"]
    executed = message.get("executed_tools", [])
    if choice["finish_reason"] != "stop" or not message.get("content"):
        raise ValueError("Research did not finish with usable text")
    if not any(t.get("name") == "browser.search" for t in executed):
        raise ValueError("No browser.search execution in provider response")
    urls = sorted(
        {
            item["url"]
            for tool in executed
            for item in ((tool.get("search_results") or {}).get("results") or [])
            if isinstance(item.get("url"), str) and item["url"].startswith(("https://", "http://"))
        }
    )
    return {
        "summary": message["content"],
        "source_urls": urls,
        "tool_names": [t.get("name") for t in executed],
        "limitation": "Retrieved sources and model-written summaries require review; search does not verify an exact event match.",
    }
