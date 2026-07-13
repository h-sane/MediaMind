"""Logging configuration for the engine process.

Emits to stderr (captured and shown live by the Electron main process, see
app/src/main/backend.ts) and to a rotating file under the app data dir, so
errors from a crashed or closed session are still inspectable afterwards.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
from typing import Callable

from mediamind.config import logs_dir

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        logs_dir() / "engine.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)


class WebSocketLogHandler(logging.Handler):
    """Fans every log record out to the /v1/progress WebSocket clients (the
    in-app dev log console), on top of the file/stream handlers above.

    Log calls can happen from any job worker thread (see core/jobs.py), not
    just the asyncio event loop thread, so `broadcast` must be marshaled onto
    the loop the same way `JobContext.report_progress` does — a raw call
    here would touch asyncio/WebSocket state from the wrong thread.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, broadcast: Callable[[logging.LogRecord], None]) -> None:
        super().__init__()
        self._loop = loop
        self._broadcast = broadcast

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._loop.call_soon_threadsafe(self._broadcast, record)
        except RuntimeError:
            pass  # loop closed (e.g. test teardown)


def attach_websocket_handler(
    loop: asyncio.AbstractEventLoop, broadcast: Callable[[logging.LogRecord], None], level: int = logging.INFO
) -> WebSocketLogHandler:
    """Installs the WS log handler on the root logger and returns it so the
    caller can remove it again on shutdown (see `detach_websocket_handler`) —
    important for tests, which create and tear down many app instances in
    one process; the root logger is a global singleton, so leaving handlers
    attached would accumulate one per test.

    Called once from the FastAPI app's lifespan, once the event loop and WS
    connection manager both exist (configure_logging() itself runs earlier,
    before either is available)."""
    handler = WebSocketLogHandler(loop, broadcast)
    handler.setLevel(level)
    logging.getLogger().addHandler(handler)
    return handler


def detach_websocket_handler(handler: WebSocketLogHandler) -> None:
    logging.getLogger().removeHandler(handler)
