"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mediamind import __version__
from mediamind.api.security import TokenAuthMiddleware
from mediamind.api.ws import ConnectionManager
from mediamind.config import browse_index_db_path, folder_stats_db_path, models_dir
from mediamind.core.folder_stats import FolderStatsIndex
from mediamind.core.jobs import JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.media_index import MediaIndex
from mediamind.core.quick_access import QuickAccessStore
from mediamind.core.recent import RecentFilesStore
from mediamind.providers.manager import ProviderManager

logger = logging.getLogger("mediamind.api")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Initialise shared state before any request arrives.
    app.state.registry = LibraryRegistry()
    app.state.media_index = MediaIndex(browse_index_db_path())
    app.state.folder_stats = FolderStatsIndex(folder_stats_db_path())
    app.state.quick_access = QuickAccessStore()
    app.state.recent_files = RecentFilesStore()
    app.state.job_manager = JobManager()
    app.state.job_manager.set_event_loop(asyncio.get_event_loop())
    app.state.connection_manager = ConnectionManager()
    app.state.job_manager.set_broadcast(app.state.connection_manager.broadcast_job)

    # Provider manager (injected in tests; created from config in production).
    if not hasattr(app.state, "providers") or app.state.providers is None:
        app.state.providers = ProviderManager(models_dir())

    yield
    # Nothing to clean up — daemon threads die with the process.


def create_app(
    token: str | None = None,
    provider_manager: ProviderManager | None = None,
) -> FastAPI:
    """Build the API app.

    `token` guards every HTTP route (see security.py). WebSocket auth is handled
    inline in the /v1/progress endpoint (middleware cannot intercept WS scopes).
    `provider_manager` is injected in tests so no real model download is needed.
    """
    _token = token or os.environ.get("MEDIAMIND_TOKEN")

    app = FastAPI(
        title="MediaMind Engine",
        version=__version__,
        docs_url="/docs",
        lifespan=_lifespan,
    )
    app.add_middleware(TokenAuthMiddleware, token=_token)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    # CORS: the Electron renderer calls this API from a different origin than
    # the engine (a different localhost port in dev, a `file://` origin once
    # packaged). Every request carries the X-MediaMind-Token header, which is
    # non-"simple" per the CORS spec and always triggers a preflight OPTIONS —
    # without this middleware that preflight gets 401'd by TokenAuthMiddleware
    # and the browser aborts the real request with "Failed to fetch" before it
    # is ever sent. Added last so it is outermost and answers preflights before
    # they reach auth. The token (not origin) is the actual access control here
    # (see security.py), so a permissive origin list is safe.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    # Store the raw token so the WS endpoint can validate it without going through
    # middleware (BaseHTTPMiddleware only sees HTTP scopes, not WebSocket upgrades).
    app.state.token = _token

    # Stash the injected provider_manager (lifespan picks it up if set).
    app.state.providers = provider_manager

    @app.get("/v1/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.websocket("/v1/progress")
    async def progress_ws(ws: WebSocket, token: str | None = Query(default=None)):
        await app.state.connection_manager.handle(
            ws,
            token=token,
            job_manager=app.state.job_manager,
            app_token=app.state.token,
        )

    from mediamind.api.routes import libraries
    from mediamind.api.routes import files
    from mediamind.api.routes import fs
    from mediamind.api.routes import fs_ops
    from mediamind.api.routes import scans
    from mediamind.api.routes import duplicates
    from mediamind.api.routes import providers
    from mediamind.api.routes import persons
    from mediamind.api.routes import organize
    from mediamind.api.routes import pending
    from mediamind.api.routes import multi_person

    app.include_router(libraries.router, prefix="/v1")
    app.include_router(files.router, prefix="/v1")
    app.include_router(fs.router, prefix="/v1")
    app.include_router(fs_ops.router, prefix="/v1")
    app.include_router(scans.router, prefix="/v1")
    app.include_router(duplicates.router, prefix="/v1")
    app.include_router(providers.router, prefix="/v1")
    app.include_router(persons.router, prefix="/v1")
    app.include_router(organize.router, prefix="/v1")
    app.include_router(pending.router, prefix="/v1")
    app.include_router(multi_person.router, prefix="/v1")

    return app
