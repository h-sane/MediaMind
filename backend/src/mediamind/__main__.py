"""Run the MediaMind engine server.

    python -m mediamind [--host 127.0.0.1] [--port 0]

With --port 0 (default) a free port is chosen and printed as a single line
`MEDIAMIND_PORT=<port>` on stdout so the Electron main process can read it.
Auth token comes from the MEDIAMIND_TOKEN environment variable (see
api/security.py).
"""

from __future__ import annotations

import argparse
import socket

import uvicorn

from mediamind.api.app import create_app
from mediamind.logging_setup import configure_logging


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def main() -> None:
    configure_logging()

    parser = argparse.ArgumentParser(prog="mediamind-server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 = pick a free port")
    args = parser.parse_args()

    port = args.port or _free_port(args.host)
    print(f"MEDIAMIND_PORT={port}", flush=True)

    uvicorn.run(create_app(), host=args.host, port=port, log_level="info")


if __name__ == "__main__":
    main()
