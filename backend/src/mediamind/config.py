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


def logs_dir() -> Path:
    d = app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def library_data_dir(library_root: Path) -> Path:
    """`.mediamind/` inside a library (created on demand)."""
    d = library_root / LIBRARY_DATA_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def browse_index_db_path() -> Path:
    """SQLite cache of "does this folder contain media below it" for the
    Explorer shell. Lives in the app data dir, not on the user's drives —
    whole-filesystem browsing must never write anything to the folders it
    looks at."""
    return app_data_dir() / "browse_index.sqlite3"


def folder_stats_db_path() -> Path:
    """SQLite cache of recursive item-count/total-bytes per folder, for the
    Explorer shell's Properties panel. Same reasoning as `browse_index_db_path`
    — lives in the app data dir, never on the user's drives."""
    return app_data_dir() / "folder_stats.sqlite3"


def quick_access_path() -> Path:
    """JSON store of the Explorer shell's pinned Quick Access folders. Lives
    in the app data dir, same reasoning as `browse_index_db_path`."""
    return app_data_dir() / "quick_access.json"


def recent_files_path() -> Path:
    """JSON store of the Explorer shell's recently-opened files (Home page).
    Lives in the app data dir, same reasoning as `browse_index_db_path`."""
    return app_data_dir() / "recent_files.json"


def fs_ops_dir() -> Path:
    """Manifests + op-log for the Explorer shell's file operations (rename/
    move/copy/delete/new-folder). Library-free browsing has no `.mediamind`
    folder to write into, so this lives in the app data dir instead —
    mirrors `browse_index_db_path`'s reasoning."""
    d = app_data_dir() / "fs_ops"
    (d / "manifests").mkdir(parents=True, exist_ok=True)
    return d
