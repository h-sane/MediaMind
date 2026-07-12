"""Path safety for the Explorer shell's whole-filesystem browsing.

Unlike the library-confined browsing in `api/routes/files.py` (every path is
resolved strictly inside one pre-registered library root), the Explorer shell
browses arbitrary OS locations starting from drives. The safety model is
therefore inverted: instead of confining to one allowed root, we resolve the
path to its real canonical location and reject it only if it falls inside a
short denylist (MediaMind's own app data, or any `.mediamind` folder).
"""

from __future__ import annotations

from pathlib import Path

from mediamind.config import LIBRARY_DATA_DIRNAME, app_data_dir


def resolve_os_path(raw: str) -> Path | None:
    """Resolve a user-supplied absolute path to a safe, real filesystem location.

    Returns None for anything unsafe or malformed: relative paths, paths that
    don't resolve to an existing file/dir, or paths inside MediaMind's own
    app data directory or any `.mediamind` folder. `Path.resolve()` collapses
    `..` and follows symlinks to their real target, so the checks below apply
    to the canonical destination, not the raw string.
    """
    if not raw:
        return None
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            return None
        resolved = candidate.resolve()
        if not resolved.exists():
            return None
        app_data = app_data_dir().resolve()
        if resolved == app_data or app_data in resolved.parents:
            return None
        if LIBRARY_DATA_DIRNAME in resolved.parts:
            return None
        return resolved
    except (OSError, ValueError):
        # Malformed path (e.g. embedded NUL) — treat as not found.
        return None
