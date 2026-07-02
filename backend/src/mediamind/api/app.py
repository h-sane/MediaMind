"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, WebSocket

from mediamind import __version__
from mediamind.api.security import TokenAuthMiddleware
from mediamind.api.ws import ConnectionManager
from mediamind.core.jobs import JobManager
from mediamind.core.libraries import LibraryRegistry


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Initialise shared state before any request arrives.
    app.state.registry = LibraryRegistry()
    app.state.job_manager = JobManager()
    app.state.job_manager.set_event_loop(asyncio.get_event_loop())
    app.state.connection_manager = ConnectionManager()
    app.state.job_manager.set_broadcast(app.state.connection_manager.broadcast_job)
    yield
    # Nothing to clean up — daemon threads die with the process.


def create_app(token: str | None = None) -> FastAPI:
    """Build the API app.

    `token` guards every HTTP route (see security.py). WebSocket auth is handled
    inline in the /v1/progress endpoint (middleware cannot intercept WS scopes).
    """
    _token = token or os.environ.get("MEDIAMIND_TOKEN")

    app = FastAPI(
        title="MediaMind Engine",
        version=__version__,
        docs_url="/docs",
        lifespan=_lifespan,
    )
    app.add_middleware(TokenAuthMiddleware, token=_token)

    # Store the raw token so the WS endpoint can validate it without going through
    # middleware (BaseHTTPMiddleware only sees HTTP scopes, not WebSocket upgrades).
    app.state.token = _token

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
    from mediamind.api.routes import scans
    from mediamind.api.routes import duplicates

    app.include_router(libraries.router, prefix="/v1")
    app.include_router(scans.router, prefix="/v1")
    app.include_router(duplicates.router, prefix="/v1")

    return app
