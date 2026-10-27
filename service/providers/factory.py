"""Build adapters for approved profiles at startup; never silently switch vendors.

Concrete adapters live beside this factory in service/providers. Add an adapter here only after
its configuration and operational controls are reviewed. There is no automatic
fallback; a provider failure returns through the shared ProviderFailure contract.
"""

from service.providers.base import TagProvider
from service.providers.gemini import GeminiProvider
from service.providers.hetzner import HetznerProvider
from service.providers.synthetic import SyntheticProvider
from service.summary.provider import SummaryProvider, SyntheticSummaryProvider


def create_provider(settings, config, client) -> TagProvider:
    """Select a reviewed adapter; dispatch admission checks credentials and budgets."""
    if settings.mode == "demo":
        return SyntheticProvider()
    if config.provider == "gemini":
        return GeminiProvider(client, config, settings.gemini_key)
    if config.provider == "hetzner":
        return HetznerProvider(client, config, settings.provider_key)
    raise ValueError("No live adapter is available for this provider")


def create_summary_provider(settings, config, client):
    """Use the same vendor selection with task-specific summary validation."""
    if settings.mode == "demo":
        return SyntheticSummaryProvider()
    return SummaryProvider(create_provider(settings, config, client), config)
