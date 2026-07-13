"""Recent files: an MRU list of files opened through the Explorer shell, for
the Home landing page (Phase N).

Same small-JSON-file, atomic-write pattern as `core/quick_access.py` — the
store holds only path + timestamp pointers, nothing about the files'
contents. A stale entry (file since deleted/moved) is simply left out of
`list()`'s validated results rather than pruned from storage, matching
`quick_access.py`'s reasoning: it self-heals if the same path reappears, and
`record()` re-adds/moves-to-front on every real open anyway.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from mediamind.config import recent_files_path

# Real Explorer's Home page shows a modest, glanceable number of recents —
# unbounded growth would make the store (and the UI list) unwieldy for no
# benefit, since anything older just scrolls off relevance.
MAX_RECENT = 30


class RecentFilesStore:
    def __init__(self, store_path: Path | None = None):
        self._path = store_path or recent_files_path()
        self._entries: list[dict[str, float | str]] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt store must never block the app; history can restart.
            return
        entries = data.get("entries", [])
        self._entries = [
            e
            for e in entries
            if isinstance(e, dict) and isinstance(e.get("path"), str) and isinstance(e.get("opened_at"), (int, float))
        ]

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"entries": self._entries}, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def list_raw(self) -> list[tuple[str, float]]:
        """Stored (path, opened_at) pairs, most-recently-opened first,
        unvalidated — callers resolve/filter for display."""
        return [(e["path"], e["opened_at"]) for e in self._entries]  # type: ignore[misc]

    def record(self, path: str) -> list[tuple[str, float]]:
        """Records `path` as just opened — moves it to the front if already
        present (re-opening a file refreshes its recency, doesn't duplicate
        it), then trims to `MAX_RECENT`."""
        self._entries = [e for e in self._entries if e["path"] != path]
        self._entries.insert(0, {"path": path, "opened_at": time.time()})
        del self._entries[MAX_RECENT:]
        self._save()
        return self.list_raw()

    def clear(self) -> None:
        """Wipes all tracked history — used when the user turns Recent files
        off (Folder Options), mirroring Explorer's "Clear File Explorer
        history" behavior so nothing already tracked lingers once disabled."""
        if self._entries:
            self._entries = []
            self._save()
