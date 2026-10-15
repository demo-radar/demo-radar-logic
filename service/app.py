"""Application factory: wire routes, lifecycle and error handling together.

Start with ``uvicorn service.app:app``. Settings are read during startup, never
at import. Provider credentials and private research data are not part of code.
"""

import sqlite3
from functools import partial

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from service.api.exception_handlers import http_error, invalid_input, rejected, unavailable_journal
from service.api.routes import router
from service.lifecycle import service_lifespan
from service.persistence.journal import AdmissionError


def create_app(settings=None, *, transport=None):
    """Create an isolated API application; no connection or inference starts yet.

    Args:
        settings: Optional Settings object; otherwise read environment at startup.
        transport: Optional HTTPX transport, used for offline provider tests.

    Returns:
        A FastAPI application with a single InferenceService during its lifespan.

    Example:
        app = create_app(Settings(token="local-test", database=Path("state.sqlite")))
    """
    app = FastAPI(
        title="DemoLogic inference",
        version="0.1.0",
        lifespan=partial(service_lifespan, settings=settings, transport=transport),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_exception_handler(RequestValidationError, invalid_input)
    app.add_exception_handler(sqlite3.Error, unavailable_journal)
    app.add_exception_handler(AdmissionError, rejected)
    app.add_exception_handler(HTTPException, http_error)
    app.include_router(router)
    return app


app = create_app()
