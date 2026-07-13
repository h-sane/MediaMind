"""App-level Explorer shell settings (currently just the Recent files
privacy toggle) — a small JSON file in the app data dir, same
small-JSON-file, atomic-write pattern as `core/quick_access.py` and
`core/recent.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from mediamind.config import settings_path

DEFAULT_RECENT_FILES_ENABLED = True


class SettingsStore:
    def __init__(self, store_path: Path | None = None):
        self._path = store_path or settings_path()
        self._recent_files_enabled = DEFAULT_RECENT_FILES_ENABLED
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt store must never block the app; settings revert to
            # defaults rather than failing startup.
            return
        enabled = data.get("recent_files_enabled")
        if isinstance(enabled, bool):
            self._recent_files_enabled = enabled

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"recent_files_enabled": self._recent_files_enabled}, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    @property
    def recent_files_enabled(self) -> bool:
        return self._recent_files_enabled

    def set_recent_files_enabled(self, enabled: bool) -> bool:
        if enabled != self._recent_files_enabled:
            self._recent_files_enabled = enabled
            self._save()
        return self._recent_files_enabled
