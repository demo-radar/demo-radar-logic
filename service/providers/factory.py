"""Choose one provider at startup; routes never select or switch vendors.

Concrete adapters live beside this factory in service/providers. Add an adapter here only after
its configuration and operational controls are reviewed. There is no automatic
fallback; a provider failure returns through the shared ProviderFailure contract.
"""

from service.providers.base import TagProvider
from service.providers.hetzner import QwenProvider
from service.providers.synthetic import SyntheticProvider


def create_provider(settings, config, client) -> TagProvider:
    """Select the adapter once at startup; never silently enable a paid provider.

    Inputs are runtime settings, an approved model config and a managed client.
    Returns SyntheticProvider in demo mode or QwenProvider for live Hetzner.
    A future GeminiProvider belongs here after its config, token normalization,
    pricing guard and tests exist. Unknown live providers fail startup.
    """
    if settings.mode == "demo":
        return SyntheticProvider()
    if config.provider == "hetzner":
        return QwenProvider(client, config, settings.provider_key)
    raise ValueError("No live adapter is available for this provider")
