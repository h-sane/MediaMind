"""FastAPI application factory."""

from __future__ import annotations

import os

from fastapi import FastAPI

from mediamind import __version__
from mediamind.api.security import TokenAuthMiddleware


def create_app(token: str | None = None) -> FastAPI:
    """Build the API app.

    `token` guards every route (see security.py). Defaults to the
    MEDIAMIND_TOKEN environment variable so a packaged backend needs no CLI
    plumbing.
    """
    app = FastAPI(title="MediaMind Engine", version=__version__, docs_url="/docs")
    app.add_middleware(TokenAuthMiddleware, token=token or os.environ.get("MEDIAMIND_TOKEN"))

    @app.get("/v1/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    # Feature routers are registered here as milestones land (libraries,
    # scans, duplicates, persons, providers, organize).
    from mediamind.api.routes import libraries

    app.include_router(libraries.router, prefix="/v1")
    return app
