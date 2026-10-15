"""Multi-label measures shared by the baseline and later model notebooks."""

import re


def parse_review_tags(value: str, allowed: set[str] | frozenset[str]) -> list[str]:
    """Read reviewed slugs without truncating three-or-more-tag human decisions.

    Commas and semicolons are accepted. Blank means missing review, not a
    confirmed empty reference set. Unknown/duplicate labels stop evaluation.
    Uncertainty scores are not probabilities and do not weight the reference.
    """
    tags = [tag.strip() for tag in re.split(r"[,;]", value) if tag.strip()]
    if not tags or len(tags) != len(set(tags)) or set(tags) - allowed:
        raise ValueError("Pilot labels must be nonempty, unique approved tag slugs")
    return tags


def multilabel_metrics(
    reference: list[list[str]], predicted: list[list[str]], tags: list[str]
) -> dict:
    """Score every attempted event, including abstentions, against complete references.

    Returns micro precision/recall/F1, exact-set match, coverage, output counts,
    and one-vs-rest TP/FP/FN/TN per tag. None denotes an undefined denominator;
    zero observed true positives does not create a fake perfect score. Macro
    scores average defined values over reference-supported tags and state how
    many were included. This function does not choose decision thresholds.
    """
    if len(reference) != len(predicted) or not reference or len(tags) != len(set(tags)):
        raise ValueError("Need equal nonempty reference/prediction lists and unique catalog tags")
    allowed = set(tags)
    for row in reference + predicted:
        if len(row) != len(set(row)) or set(row) - allowed:
            raise ValueError("Unknown or duplicate tags in evaluation")
    truth, guesses = list(map(set, reference)), list(map(set, predicted))

    def divide(a, b):
        return a / b if b else None

    per_tag = {}
    for tag in tags:
        tp = sum(tag in a and tag in b for a, b in zip(truth, guesses))
        fp = sum(tag not in a and tag in b for a, b in zip(truth, guesses))
        fn = sum(tag in a and tag not in b for a, b in zip(truth, guesses))
        per_tag[tag] = {
            "support": tp + fn,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": len(truth) - tp - fp - fn,
            "precision": divide(tp, tp + fp),
            "recall": divide(tp, tp + fn),
            "f1": divide(2 * tp, 2 * tp + fp + fn),
        }
    tp, fp, fn = (sum(row[key] for row in per_tag.values()) for key in ("tp", "fp", "fn"))
    result = {
        "records": len(truth),
        "micro_precision": divide(tp, tp + fp),
        "micro_recall": divide(tp, tp + fn),
        "micro_f1": divide(2 * tp, 2 * tp + fp + fn),
        "coverage": sum(bool(row) for row in guesses) / len(truth),
        "exact_match": sum(a == b for a, b in zip(truth, guesses)) / len(truth),
        "more_than_two": sum(len(row) > 2 for row in guesses),
        "abstentions": sum(not row for row in guesses),
        "per_tag": per_tag,
    }
    for name in ("precision", "recall", "f1"):
        values = [row[name] for row in per_tag.values() if row["support"] and row[name] is not None]
        result[f"macro_{name}_supported"] = sum(values) / len(values) if values else None
        result[f"macro_{name}_tag_count"] = len(values)
    return result
