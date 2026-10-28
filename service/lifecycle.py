"""Open application resources once, then drain active inference before shutdown.

This is the composition point for the coordinator, journal and provider. Routes
receive the assembled service through application state rather than creating
clients or database connections for each request.
"""

from contextlib import asynccontextmanager

import httpx

from service.config import Settings
from service.persistence.locking import server_lock
from service.task_factory import TaskServiceFactory


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
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(runtime.timeout_seconds, connect=10),
        limits=httpx.Limits(max_connections=1),
    ) as client:
        services = TaskServiceFactory(runtime, client).create()
        services.attach(app.state)
        try:
            yield
        finally:
            await services.close()
