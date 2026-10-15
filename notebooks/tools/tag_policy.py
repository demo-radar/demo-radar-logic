"""Response validation for the versioned three-tag notebook experiment."""

import json


def parse_tied_tags(content, tags):
    """Validate at most three distinct tags and the required qualitative tie reason.

    Three tags require tie=true and a nonempty explanation. Zero to two require
    tie=false and an empty reason. Validation checks structure, not whether the
    title actually supports the explanation; the review table checks that claim.
    Array order ranks tags, making the last item the proposed third tag.
    """
    obj = json.loads(content)
    if not isinstance(obj, dict) or set(obj) != {"tags", "tie", "tie_reason"}:
        raise ValueError("Expected tags, tie and tie_reason")
    values = obj["tags"]
    if (
        not isinstance(values, list)
        or len(values) > 3
        or any(not isinstance(t, str) or t not in tags for t in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError("Expected zero to three distinct approved tags")
    if type(obj["tie"]) is not bool or not isinstance(obj["tie_reason"], str):
        raise ValueError("Tie must be boolean and reason must be text")
    if len(values) == 3:
        if not obj["tie"] or not obj["tie_reason"].strip():
            raise ValueError("Three tags require a tie and a title-grounded reason")
    elif obj["tie"] or obj["tie_reason"] != "":
        raise ValueError("Zero to two tags require false tie and empty reason")
    return values
