"""Strict response validation for the retrospective uncertainty diagnostic.

Prompts, warning rules, selection and evaluation stay visible in Notebook 19.
These self-reports are review signals, not calibrated probabilities.
"""

import json


def decode_confidence(body, tags):
    """Require two certainty levels, one cause and a short explanation.

    The diagnostic evaluates a saved answer and cannot replace its tags.
    Reject malformed responses instead of silently treating them as confident.
    ``tags`` is accepted for the shared transport decoder interface.
    """
    if body.get("status") != "completed":
        raise ValueError("Incomplete response")
    text = "\n".join(
        c.get("text", "")
        for step in body.get("steps", [])
        if step.get("type") == "model_output"
        for c in step.get("content", [])
        if c.get("type") == "text"
    ).strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    obj = json.loads(text)
    if not isinstance(obj, dict) or set(obj) != {"support", "completeness", "cause", "reason"}:
        raise ValueError("Unexpected uncertainty fields")
    if obj["support"] not in ("high", "medium", "low") or obj["completeness"] not in (
        "high",
        "medium",
        "low",
    ):
        raise ValueError("Invalid certainty level")
    if obj["cause"] not in ("none", "missing_context", "rubric_boundary", "unsupported_tag"):
        raise ValueError("Invalid cause")
    if not isinstance(obj["reason"], str) or not obj["reason"].strip():
        raise ValueError("Missing explanation")
    return {"predicted": [], "audit": obj}
