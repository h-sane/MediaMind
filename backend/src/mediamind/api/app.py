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
from mediamind.logging_setup import attach_websocket_handler, detach_websocket_handler
from mediamind.core.folder_stats import FolderStatsIndex
from mediamind.core.jobs import JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.media_index import MediaIndex
from mediamind.core.quick_access import QuickAccessStore
from mediamind.core.recent import RecentFilesStore
from mediamind.core.settings import SettingsStore
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
    app.state.settings = SettingsStore()
    app.state.job_manager = JobManager()
    app.state.job_manager.set_event_loop(asyncio.get_event_loop())
    app.state.connection_manager = ConnectionManager()
    app.state.job_manager.set_broadcast(app.state.connection_manager.broadcast_job)
    # Fans every log record out to the in-app dev log console over the same
    # WS channel — a no-op in practice unless a client has it open (see
    # ConnectionManager.broadcast_log).
    log_handler = attach_websocket_handler(asyncio.get_event_loop(), app.state.connection_manager.broadcast_log)

    # Provider manager (injected in tests; created from config in production).
    if not hasattr(app.state, "providers") or app.state.providers is None:
        app.state.providers = ProviderManager(models_dir())

    # Performance & Ingest V4: always-on incremental ingest. Idle (no walking,
    # no model loaded) unless the user has opted in via the auto-scan setting.
    # LibraryWatcher (native FS events, poll fallback) reports just the
    # changed paths; IngestWorker processes only those paths through the
    # shared per-file pipeline (core/ingest.py) instead of re-running a
    # whole-folder scan. See docs/PERFORMANCE_AND_INGEST_V4_PLAN.md.
    from mediamind.core.ingest_worker import IngestWorker
    from mediamind.core.watcher import LibraryWatcher

    pm = app.state.providers
    _default_entry = next((e for e in pm.entries() if pm.is_installed(e.id)), None)

    app.state.ingest_worker = IngestWorker(
        app.state.registry,
        app.state.job_manager,
        provider_factory=(lambda: pm.create(_default_entry.id)) if _default_entry else None,
        provider_id=_default_entry.id if _default_entry else None,
        enabled=lambda: app.state.settings.auto_scan_enabled,
    )
    app.state.ingest_worker.start()

    def _on_watcher_change(lib, changed_paths: list[str]) -> None:
        app.state.ingest_worker.enqueue(lib.id, changed_paths)

    app.state.watcher = LibraryWatcher(
        app.state.registry,
        _on_watcher_change,
        enabled=lambda: app.state.settings.auto_scan_enabled,
    )
    app.state.watcher.start()

    yield
    # Daemon threads die with the process, nothing to join. The log handler
    # is the one thing that must be detached — it's registered on the root
    # logger, a global singleton outside this app instance's lifetime, so
    # leaving it attached after shutdown would accumulate one per app
    # instance created (e.g. once per test in the test suite).
    detach_websocket_handler(log_handler)


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
    from mediamind.api.routes import bindings
    from mediamind.api.routes import faces_prep
    from mediamind.api.routes import materialize
    from mediamind.api.routes import duplicate_flags

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
    app.include_router(bindings.router, prefix="/v1")
    app.include_router(faces_prep.router, prefix="/v1")
    app.include_router(materialize.router, prefix="/v1")
    app.include_router(duplicate_flags.router, prefix="/v1")

    return app
