"""Open application resources once, then drain active inference before shutdown.

This is the composition point for the coordinator, journal and provider. Routes
receive the assembled service through application state rather than creating
clients or database connections for each request.
"""

from contextlib import asynccontextmanager

import httpx

from service.config import InferenceConfig, Settings
from service.inference.coordinator import InferenceService
from service.persistence.journal import Journal
from service.persistence.locking import server_lock
from service.providers.factory import create_provider
from service.summary.config import SummaryConfig
from service.summary.coordinator import SummaryService
from service.summary.provider import HetznerSummaryProvider, SyntheticSummaryProvider


@asynccontextmanager
async def service_lifespan(app, *, settings=None, transport=None):
    """Open resources at startup and drain work even on exceptional shutdown.

    Args:
        app: FastAPI application; its state receives the InferenceService.
        settings: Optional explicit settings for local/offline tests.
        transport: Optional HTTPX mock transport; absent in normal deployment.
    Yields:
        Control to the web server until shutdown, then closes owned resources.
    """
    runtime = settings or Settings.from_env()
    with server_lock(runtime.database):
        async with _locked_service_lifespan(app, runtime=runtime, transport=transport):
            yield


@asynccontextmanager
async def _locked_service_lifespan(app, *, runtime, transport):
    """Compose and drain resources while holding the shared server lock."""
    config = InferenceConfig(runtime.root, runtime.config_id)
    journal = Journal(runtime.database, max_attempts=runtime.max_attempts_per_event)
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(runtime.timeout_seconds, connect=10),
        limits=httpx.Limits(max_connections=1),
    ) as client:
        app.state.service = InferenceService(
            runtime, config, journal, create_provider(runtime, config, client)
        )
        app.state.summary = None
        if runtime.summary_enabled:
            summary_config = SummaryConfig(runtime.root, runtime.summary_config_id)
            summary_provider = (
                SyntheticSummaryProvider()
                if runtime.mode == "demo"
                else HetznerSummaryProvider(client, summary_config, runtime.provider_key)
            )
            app.state.summary = SummaryService(
                runtime,
                summary_config,
                Journal(runtime.database, max_attempts=runtime.summary_max_attempts),
                summary_provider,
            )
        try:
            yield
        finally:
            await app.state.service.close()
            if app.state.summary is not None:
                await app.state.summary.close()
