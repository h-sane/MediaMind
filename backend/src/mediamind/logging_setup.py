"""Logging configuration for the engine process.

Emits to stderr (captured and shown live by the Electron main process, see
app/src/main/backend.ts) and to a rotating file under the app data dir, so
errors from a crashed or closed session are still inspectable afterwards.
"""

from __future__ import annotations

import logging
import logging.handlers

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
