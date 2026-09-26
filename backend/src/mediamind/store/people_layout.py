"""People view layout: pins and user-made collections (design:
docs/PEOPLE_VIEW_V2_DESIGN.md).

One small JSON file in the app data dir, mirroring `core/quick_access.py`. It
stores only pointers and names — moving a person into a collection or pinning
a card never touches a file on disk (safety rule 4).

Item keys are flat strings so a person keeps their pin/collection when naming
or linking changes which cross-library identity they belong to:
  - `p:<library_id>:<local_person_id>` — one library's person (a linked identity
    has several; it matches a pin/collection if *any* of its keys is stored)
  - `f:<absolute folder path>`         — a folder card
  - `c:<collection id>`                — a collection (pin only)
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from mediamind.config import people_layout_path


def person_key(library_id: str, local_person_id: int) -> str:
    return f"p:{library_id}:{local_person_id}"


def folder_key(abs_path: str) -> str:
    return f"f:{abs_path}"


class PeopleLayoutStore:
    def __init__(self, store_path: Path | None = None):
        self._path = store_path or people_layout_path()
        self._lock = threading.Lock()
        self._pins: list[str] = []
        self._hidden: list[str] = []
        self._collections: list[dict] = []  # {"id", "name", "members": [key, ...]}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt store must never block the app; pins can be re-added.
            return
        self._pins = [k for k in data.get("pins", []) if isinstance(k, str)]
        self._hidden = [k for k in data.get("hidden", []) if isinstance(k, str)]
        for c in data.get("collections", []):
            if isinstance(c, dict) and isinstance(c.get("id"), str) and isinstance(c.get("name"), str):
                members = [m for m in c.get("members", []) if isinstance(m, str)]
                self._collections.append({"id": c["id"], "name": c["name"], "members": members})

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        payload = {"pins": self._pins, "hidden": self._hidden, "collections": self._collections}
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    # -- pins ---------------------------------------------------------------

    def pins(self) -> list[str]:
        with self._lock:
            return list(self._pins)

    def pin(self, key: str) -> None:
        with self._lock:
            if key not in self._pins:
                self._pins.append(key)
                self._save()

    def unpin(self, keys: list[str]) -> None:
        """Removes every given key — an identity with several member keys is
        unpinned in one call."""
        with self._lock:
            kept = [k for k in self._pins if k not in set(keys)]
            if len(kept) != len(self._pins):
                self._pins = kept
                self._save()

    def reorder_pins(self, ordered: list[str]) -> None:
        """Applies a caller-supplied order; unknown keys are ignored and any
        stored pin missing from `ordered` keeps its place at the end."""
        with self._lock:
            known = set(self._pins)
            head = [k for k in dict.fromkeys(ordered) if k in known]
            self._pins = head + [k for k in self._pins if k not in set(head)]
            self._save()

    # -- hidden people ------------------------------------------------------

    def hidden(self) -> list[str]:
        with self._lock:
            return list(self._hidden)

    def hide(self, keys: list[str]) -> None:
        """Ignore these people everywhere in the People view (and drop their pin
        and collection place); their photos and scan data are untouched."""
        with self._lock:
            gone = set(keys)
            self._hidden.extend(k for k in dict.fromkeys(keys) if k not in self._hidden)
            self._pins = [k for k in self._pins if k not in gone]
            for c in self._collections:
                c["members"] = [m for m in c["members"] if m not in gone]
            self._save()

    def unhide(self, keys: list[str]) -> None:
        with self._lock:
            gone = set(keys)
            self._hidden = [k for k in self._hidden if k not in gone]
            self._save()

    # -- collections --------------------------------------------------------

    def collections(self) -> list[dict]:
        with self._lock:
            return [{**c, "members": list(c["members"])} for c in self._collections]

    def create_collection(self, name: str) -> dict:
        with self._lock:
            c = {"id": uuid.uuid4().hex[:12], "name": name.strip(), "members": []}
            self._collections.append(c)
            self._save()
            return {**c, "members": []}

    def rename_collection(self, collection_id: str, name: str) -> bool:
        with self._lock:
            c = self._find(collection_id)
            if c is None:
                return False
            c["name"] = name.strip()
            self._save()
            return True

    def delete_collection(self, collection_id: str) -> bool:
        """Members return to their automatic place; also drops a pin on it."""
        with self._lock:
            c = self._find(collection_id)
            if c is None:
                return False
            self._collections.remove(c)
            self._pins = [k for k in self._pins if k != f"c:{collection_id}"]
            self._save()
            return True

    def add_members(self, collection_id: str, keys: list[str]) -> bool:
        """A key lives in at most one collection: adding it here removes it
        from any other (a drag moves, it does not copy)."""
        with self._lock:
            c = self._find(collection_id)
            if c is None:
                return False
            moving = set(keys)
            for other in self._collections:
                other["members"] = [m for m in other["members"] if m not in moving]
            c["members"].extend(k for k in dict.fromkeys(keys))
            self._save()
            return True

    def remove_members(self, keys: list[str]) -> None:
        with self._lock:
            gone = set(keys)
            for c in self._collections:
                c["members"] = [m for m in c["members"] if m not in gone]
            self._save()

    def _find(self, collection_id: str) -> dict | None:
        return next((c for c in self._collections if c["id"] == collection_id), None)
