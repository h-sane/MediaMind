"""WebSocket progress channel: WS /v1/progress

All job progress is broadcast here. Clients subscribe once and filter by
job_id. A single global endpoint avoids per-job connect-race problems.

Auth: BaseHTTPMiddleware only intercepts HTTP scopes, not WebSocket upgrades,
and the browser WebSocket API cannot send custom headers. We therefore validate
the session token from the `token` query parameter using hmac.compare_digest
(token-in-URL is acceptable here: loopback-only, no intermediaries, and uvicorn
access logs are local-only).
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from mediamind.core.jobs import Job, JobManager


def _job_to_msg(job: Job) -> str:
    return json.dumps({
        "msg_type": "job",  # envelope discriminator (avoids collision with job.type)
        "id": job.id,
        "library_id": job.library_id,
        "type": job.type,
        "state": job.state,
        "phase": job.phase,
        "done": job.done,
        "total": job.total,
        "error": job.error,
        "result": job.result,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    })


def _log_to_msg(record: logging.LogRecord) -> str:
    return json.dumps({
        "msg_type": "log",  # envelope discriminator, sibling to "job" above
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
        "ts": record.created,
    })


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts job updates."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    def broadcast_job(self, job: Job) -> None:
        """Called from the asyncio event loop (via call_soon_threadsafe)."""
        msg = _job_to_msg(job)
        for ws in list(self._clients):
            asyncio.ensure_future(ws.send_text(msg))

    def broadcast_log(self, record: logging.LogRecord) -> None:
        """Called from the asyncio event loop (via call_soon_threadsafe, see
        logging_setup.WebSocketLogHandler) — feeds the in-app dev log console.
        No-op with zero clients connected, which is the common case (the
        panel is opt-in), so this never does real work unless someone has it
        open."""
        if not self._clients:
            return
        try:
            msg = _log_to_msg(record)
        except Exception:
            return  # never let a malformed log record break logging itself
        for ws in list(self._clients):
            asyncio.ensure_future(ws.send_text(msg))

    async def handle(self, ws: WebSocket, token: str | None, job_manager: JobManager, app_token: str | None) -> None:
        # Validate token before accepting the connection.
        if app_token is not None:
            supplied = token or ""
            if not hmac.compare_digest(supplied, app_token):
                await ws.close(code=4401)
                return

        await ws.accept()
        self._clients.add(ws)
        try:
            # Send a snapshot of all non-terminal jobs so reconnecting clients resync.
            for job in job_manager.active_jobs():
                await ws.send_text(_job_to_msg(job))

            # Keep the socket alive; we push, clients don't send anything.
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            self._clients.discard(ws)
