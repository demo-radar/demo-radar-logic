"""Task output rules shared by adapters and the execution controller."""

from demo_logic.taxonomy import topic_tags
from service.providers.base import ProviderFailure, response_metadata


def validate_tags(tags, metadata):
    """Reject invalid tag sets while preserving known provider usage."""
    if (
        not isinstance(tags, list)
        or len(tags) > 2
        or any(not isinstance(tag, str) or tag not in topic_tags("v2") for tag in tags)
        or len(set(tags)) != len(tags)
        or not isinstance(metadata, dict)
    ):
        raise ProviderFailure("invalid_provider_response", metadata=response_metadata(metadata))
