"""Session-token auth for the localhost API.

The Electron main process generates a random token, passes it to the backend
via the MEDIAMIND_TOKEN environment variable, and sends it on every request as
the `X-MediaMind-Token` header. Requests without the correct token are
rejected, so no other local process can drive the engine.

If no token is configured (bare development runs), auth is disabled.
"""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

TOKEN_HEADER = "X-MediaMind-Token"


class TokenAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str | None):
        super().__init__(app)
        self._token = token or None

    async def dispatch(self, request: Request, call_next):
        if self._token is not None:
            sent = request.headers.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(sent, self._token):
                return JSONResponse(status_code=401, content={"detail": "invalid token"})
        return await call_next(request)
