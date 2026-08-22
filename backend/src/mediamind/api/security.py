"""Session-token auth for the localhost API.

The Electron main process generates a random token, passes it to the backend
via the MEDIAMIND_TOKEN environment variable, and sends it on every request as
the `X-MediaMind-Token` header. Requests without the correct token are
rejected, so no other local process can drive the engine.

If no token is configured (bare development runs), auth is disabled.
"""

from __future__ import annotations

import hmac

from fastapi.responses import JSONResponse

TOKEN_HEADER = "X-MediaMind-Token"
_TOKEN_HEADER_BYTES = TOKEN_HEADER.lower().encode("latin-1")


class TokenAuthMiddleware:
    """Pure-ASGI token gate.

    Deliberately not a `BaseHTTPMiddleware`: that wraps every request in its own
    anyio sub-task over memory streams, which is per-request overhead that
    compounds at the hundreds of thumbnail requests a single folder can fire.
    Only HTTP scopes are gated — WebSocket auth is validated inline in the
    /v1/progress endpoint.
    """

    def __init__(self, app, token: str | None):
        self.app = app
        self._token = token or None

    async def __call__(self, scope, receive, send):
        if self._token is not None and scope["type"] == "http":
            sent = ""
            for name, value in scope["headers"]:
                if name == _TOKEN_HEADER_BYTES:
                    sent = value.decode("latin-1")
                    break
            if not hmac.compare_digest(sent, self._token):
                await JSONResponse(status_code=401, content={"detail": "invalid token"})(
                    scope, receive, send
                )
                return
        await self.app(scope, receive, send)
