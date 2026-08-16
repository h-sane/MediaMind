"""App-level Explorer shell settings (Recent files privacy toggle and the
Phase-8 auto-scan toggle) — a small JSON file in the app data dir, same
small-JSON-file, atomic-write pattern as `core/quick_access.py` and
`core/recent.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from mediamind.config import settings_path

DEFAULT_RECENT_FILES_ENABLED = True
# Off by default: auto-scanning fires heavy background dedupe/face jobs on the
# user's folders without them asking, so it stays opt-in (safety before
# performance). See core/watcher.py.
# Three tiers: "off" (no watching), "libraries" (watch registered library
# folders — the original single-flag behavior), "system" (also watch whole
# fixed drives for new media via core/discovery.py's cheap Tier-3 tally, no
# ingest pipeline run outside registered libraries).
AUTO_SCAN_MODES = ("off", "libraries", "system")
DEFAULT_AUTO_SCAN_MODE = "off"


class SettingsStore:
    def __init__(self, store_path: Path | None = None):
        self._path = store_path or settings_path()
        self._recent_files_enabled = DEFAULT_RECENT_FILES_ENABLED
        self._auto_scan_mode = DEFAULT_AUTO_SCAN_MODE
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
        mode = data.get("auto_scan_mode")
        if mode in AUTO_SCAN_MODES:
            self._auto_scan_mode = mode
        elif "auto_scan_mode" not in data:
            # Pre-V3 store: a bare `auto_scan_enabled` boolean, no mode key yet.
            legacy = data.get("auto_scan_enabled")
            if isinstance(legacy, bool):
                self._auto_scan_mode = "libraries" if legacy else "off"

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "recent_files_enabled": self._recent_files_enabled,
                    "auto_scan_mode": self._auto_scan_mode,
                },
                indent=2,
            ),
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

    @property
    def auto_scan_mode(self) -> str:
        return self._auto_scan_mode

    def set_auto_scan_mode(self, mode: str) -> str:
        if mode not in AUTO_SCAN_MODES:
            raise ValueError(f"invalid auto_scan_mode: {mode!r} (must be one of {AUTO_SCAN_MODES})")
        if mode != self._auto_scan_mode:
            self._auto_scan_mode = mode
            self._save()
        return self._auto_scan_mode

    @property
    def auto_scan_enabled(self) -> bool:
        return self._auto_scan_mode != "off"

    def set_auto_scan_enabled(self, enabled: bool) -> bool:
        """Back-compat shim for the pre-V3 boolean API — maps onto the
        `"off"`/`"libraries"` tiers so existing callers keep working
        unchanged until they're migrated to `set_auto_scan_mode`."""
        self.set_auto_scan_mode("libraries" if enabled else "off")
        return self.auto_scan_enabled
