"""Application paths and configuration.

Per-library data (index, manifests) lives inside the library itself under
`.mediamind/` — filesystem-first, it travels with the folder. Only app-level
state that is not tied to any library lives in the user config dir:
the registry of known libraries and downloaded model files.
"""

from __future__ import annotations

import hashlib
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


def thumbnail_cache_dir() -> Path:
    """Persistent on-disk thumbnail/preview cache, keyed by file identity.

    Loose JPEGs under a hashed, sharded path so relaunching the app never
    re-decodes a file it has already thumbnailed — the single biggest felt
    speed win. Lives in the app data dir, same reasoning as
    `browse_index_db_path`: whole-filesystem browsing must never write to the
    folders it looks at. Rebuildable at any time (safe to delete)."""
    d = app_data_dir() / "thumb_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def face_thumb_cache_dir() -> Path:
    """Persistent on-disk cache of cropped face thumbnails for the People view.

    Lives in the app data dir, NOT inside `<library>/.mediamind/` — the whole
    point (ADR-0004) is that a Person's face crops keep rendering when the
    library's drive (Cryptomator, cloud-backed, removable) is unmounted. An
    on-drive cache vanishes with the drive; this one survives. Namespaced per
    library by the caller so relative-path keys can't collide across libraries.
    Rebuildable at any time (safe to delete)."""
    d = app_data_dir() / "face_thumb_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def library_data_dir(library_root: Path) -> Path:
    """`.mediamind/` inside a library — manifests, audit trail, folder-face
    thumbs. Created on demand, so calling it requires the drive to be mounted.
    The index DB used to live here too; it now lives off-drive, see
    `library_index_db_path`."""
    d = library_root / LIBRARY_DATA_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def library_index_db_path(library_root: Path) -> Path:
    """Per-library index DB, relocated OFF the library drive into app-data so
    the People view / catalog survive the drive (Cryptomator, cloud-backed,
    removable) unmounting — ADR-0004.

    Keyed by a stable hash of the library's resolved root path, not the registry
    id: the resolved path is what every caller already holds, needs no registry
    lookup, and survives a registry rebuild. `normcase` folds Windows path
    casing/separators so the key is mount-state-independent. Most of the index
    is rebuildable by rescan, but curated data (person names, rejections,
    bindings) is NOT — so migration into this location is copy-then-delete and
    never fabricates an empty index while the drive is offline (see
    `store.db.open_library_db`)."""
    key = hashlib.sha1(os.path.normcase(str(library_root)).encode("utf-8")).hexdigest()[:16]
    return app_data_dir() / "library_index" / key / "index.db"


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


def people_layout_path() -> Path:
    """JSON store of the People view's pins and user-made collections. App-level
    (not per-library) because both span libraries; holds only pointers, never
    user media. Same reasoning as `browse_index_db_path`."""
    return app_data_dir() / "people_layout.json"


def settings_path() -> Path:
    """JSON store of the Explorer shell's user-facing app settings (e.g.
    whether Recent files is tracked at all). Lives in the app data dir, same
    reasoning as `browse_index_db_path`."""
    return app_data_dir() / "settings.json"


def discovery_db_path() -> Path:
    """SQLite tally of unregistered folders with new media, for the Tier-3
    "system" auto-scan mode. Lives in the app data dir, same reasoning as
    `browse_index_db_path` — never written into the folders it watches."""
    return app_data_dir() / "discovery.sqlite3"


def fs_ops_dir() -> Path:
    """Manifests + op-log for the Explorer shell's file operations (rename/
    move/copy/delete/new-folder). Library-free browsing has no `.mediamind`
    folder to write into, so this lives in the app data dir instead —
    mirrors `browse_index_db_path`'s reasoning."""
    d = app_data_dir() / "fs_ops"
    (d / "manifests").mkdir(parents=True, exist_ok=True)
    return d


def journals_dir() -> Path:
    """Write-ahead journals for in-flight file-move batches (ADR-0005). Lives
    off-drive in app-data so a journal survives the very unmount/crash it
    guards against and is found on next launch for auto-resume. A journal file
    exists only while a `safety.execute()` batch is mid-run; see
    `core/journal.py`."""
    d = app_data_dir() / "journals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def global_moves_dir() -> Path:
    """Manifests for cross-library global-person physical moves
    (`core/global_people.py`'s `execute_move_plan`). A move spans two
    libraries, so it has no single `.mediamind` home either — same reasoning
    as `fs_ops_dir()`."""
    d = app_data_dir() / "global_moves"
    (d / "manifests").mkdir(parents=True, exist_ok=True)
    return d


def replace_file(tmp: Path, dest: Path) -> None:
    """`tmp.replace(dest)` that survives Windows briefly refusing it: another process (antivirus,
    the search indexer, a backup tool) holding the just-written file open makes the rename fail
    with PermissionError for a few milliseconds. Tries for about a second, then raises."""
    import time

    for attempt in range(20):
        try:
            tmp.replace(dest)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)
