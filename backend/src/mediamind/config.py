"""Application paths and configuration.

Per-library data (index, manifests) lives inside the library itself under
`.mediamind/` — filesystem-first, it travels with the folder. Only app-level
state that is not tied to any library lives in the user config dir:
the registry of known libraries and downloaded model files.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MediaMind"
LIBRARY_DATA_DIRNAME = ".mediamind"


def app_data_dir() -> Path:
    """Cross-platform per-user app data directory (created on demand)."""
    override = os.environ.get("MEDIAMIND_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def models_dir() -> Path:
    d = app_data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def library_data_dir(library_root: Path) -> Path:
    """`.mediamind/` inside a library (created on demand)."""
    d = library_root / LIBRARY_DATA_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d
