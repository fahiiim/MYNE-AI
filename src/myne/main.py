from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from myne import __version__
from myne.api.errors import register_exception_handlers
from myne.api.middleware import RequestContextMiddleware
from myne.api.routes import api_router, health
from myne.container import ContainerFactory, build_container
from myne.core.config import Settings, get_settings
from myne.core.logging import configure_logging


def create_app(
    settings: Settings | None = None,
    *,
    container_factory: ContainerFactory = build_container,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.json_logs)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with container_factory(settings) as container:
            app.state.container = container
            yield

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
            expose_headers=["x-request-id"],
        )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router)
    return app
