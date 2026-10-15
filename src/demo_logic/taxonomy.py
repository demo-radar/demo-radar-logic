"""Versioned topic catalogs; taxonomy versions are independent of file schemas."""

COMMON_TAGS = frozenset(
    {
        "environment",
        "mobility",
        "housing",
        "work",
        "social-issues",
        "education",
        "lgbtq",
        "human-rights",
        "politics",
        "culture",
        "religion",
    }
)
TAGS_BY_VERSION = {
    "v1": COMMON_TAGS | {"conflict"},
    "v2": COMMON_TAGS | {"international-politics"},
}
CURRENT_TAXONOMY = "v2"
# Automatic renames only. A narrower politics definition needs human review.
V1_TO_V2 = {"conflict": "international-politics"}


def topic_tags(version: str) -> frozenset[str]:
    """Return a known catalog, rejecting unknown versions rather than guessing."""
    if version not in TAGS_BY_VERSION:
        raise ValueError(f"Unsupported taxonomy version: {version!r}")
    return TAGS_BY_VERSION[version]
