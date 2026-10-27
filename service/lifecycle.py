"""Open application resources once, then drain active inference before shutdown.

This is the composition point for the coordinator, journal and provider. Routes
receive the assembled service through application state rather than creating
clients or database connections for each request.
"""

from contextlib import asynccontextmanager

import httpx

from service.config import InferenceConfig, Settings
from service.inference.coordinator import InferenceService
from service.inference.profiles import TaskProfiles
from service.persistence.journal import Journal
from service.persistence.locking import server_lock
from service.providers.factory import create_provider, create_summary_provider
from service.summary.config import SummaryConfig
from service.summary.coordinator import SummaryService


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
        app.state.profiles = TaskProfiles()
        app.state.profiles.add(app.state.service)
        for version in dict.fromkeys((*runtime.retained_tag_configs, "gemini-v4-v1")):
            if version != config.version:
                retained = InferenceConfig(runtime.root, version)
                app.state.profiles.add(
                    InferenceService(
                        runtime, retained, journal, create_provider(runtime, retained, client)
                    )
                )
        app.state.summary = None
        if runtime.summary_enabled:
            versions = dict.fromkeys(
                (
                    runtime.summary_config_id,
                    *runtime.retained_summary_configs,
                    "hetzner-daily-v1",
                    "gemini-daily-v1",
                )
            )
            for version in versions:
                summary_config = SummaryConfig(runtime.root, version)
                service = SummaryService(
                    runtime,
                    summary_config,
                    Journal(runtime.database, max_attempts=runtime.summary_max_attempts),
                    create_summary_provider(runtime, summary_config, client),
                )
                app.state.profiles.add(service)
                if version == runtime.summary_config_id:
                    app.state.summary = service
        try:
            yield
        finally:
            for service in app.state.profiles.services.values():
                await service.close()
