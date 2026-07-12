"""Quick Access: user-pinned folders for the Explorer shell's nav pane.

A small JSON file in the app data dir, mirroring `core/libraries.py`'s
registry pattern — it stores only path pointers, nothing about the folders'
contents. A stale pin (folder deleted, drive unplugged) is simply left out of
`list()`'s validated results rather than being pruned from storage, so it
reappears automatically if the drive comes back (same reasoning `core/
libraries.py` applies to a missing library root, just without the "unregister
requires an explicit action" step since a pin is not user data).
"""

from __future__ import annotations

import json
from pathlib import Path

from mediamind.config import quick_access_path


class QuickAccessStore:
    def __init__(self, store_path: Path | None = None):
        self._path = store_path or quick_access_path()
        self._pins: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt store must never block the app; pins can be re-added.
            return
        self._pins = [p for p in data.get("pins", []) if isinstance(p, str)]

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"pins": self._pins}, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def list_raw(self) -> list[str]:
        """Stored pin paths, unvalidated — callers resolve/filter for display."""
        return list(self._pins)

    def pin(self, path: str) -> list[str]:
        if path not in self._pins:
            self._pins.append(path)
            self._save()
        return self.list_raw()

    def unpin(self, path: str) -> list[str]:
        if path in self._pins:
            self._pins.remove(path)
            self._save()
        return self.list_raw()

    def reorder(self, paths: list[str]) -> list[str]:
        """Applies a caller-supplied order (drag-reorder in the nav pane).
        Defensive against a stale/partial list: anything in `paths` that
        isn't currently pinned is ignored, and any current pin missing from
        `paths` keeps its relative order at the end — so a client racing a
        concurrent pin/unpin can never lose or invent a pin, only reorder
        the ones both sides agree exist."""
        known = set(self._pins)
        new_order = [p for p in paths if p in known]
        new_order += [p for p in self._pins if p not in new_order]
        if new_order != self._pins:
            self._pins = new_order
            self._save()
        return self.list_raw()
