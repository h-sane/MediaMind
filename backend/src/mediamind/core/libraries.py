"""Registry of libraries (folders the user has granted MediaMind).

The registry is a small JSON file in the app data dir. It stores only
*pointers* to libraries — all per-library data lives inside the library's own
`.mediamind/` folder, so a library remains portable and the registry can
always be rebuilt by re-adding folders.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from mediamind.config import app_data_dir, library_data_dir

REGISTRY_FILENAME = "libraries.json"


@dataclass
class Library:
    id: str
    path: str
    name: str

    @property
    def root(self) -> Path:
        return Path(self.path)


class LibraryRegistry:
    def __init__(self, registry_path: Path | None = None):
        self._path = registry_path or (app_data_dir() / REGISTRY_FILENAME)
        self._libraries: dict[str, Library] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt registry must never block the app; folders can be re-added.
            return
        for item in data.get("libraries", []):
            lib = Library(**item)
            self._libraries[lib.id] = lib

    def _save(self) -> None:
        payload = {"libraries": [asdict(lib) for lib in self._libraries.values()]}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def list(self) -> list[Library]:
        return sorted(self._libraries.values(), key=lambda lib: lib.name.lower())

    def get(self, library_id: str) -> Library | None:
        return self._libraries.get(library_id)

    def add(self, path: Path) -> Library:
        root = path.expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        for lib in self._libraries.values():
            if Path(lib.path) == root:
                return lib  # already registered — idempotent
        lib = Library(id=uuid.uuid4().hex[:12], path=str(root), name=root.name)
        library_data_dir(root)  # create .mediamind/ up front
        self._libraries[lib.id] = lib
        self._save()
        return lib

    def remove(self, library_id: str) -> bool:
        """Unregister only. Never touches the folder or its contents."""
        if library_id in self._libraries:
            del self._libraries[library_id]
            self._save()
            return True
        return False
