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

from mediamind.config import app_data_dir, library_data_dir, replace_file
from mediamind.core.concurrency import TIMED_OUT, run_with_timeout

REGISTRY_FILENAME = "libraries.json"

# Resolving/stat-ing the path being registered is blocking I/O with no other
# bound on its time: on a wedged network share or a locked encrypted-drive
# vault (Cryptomator/WinFsp), `resolve()`/`is_dir()` can hang for the OS
# network timeout — long enough that the HTTP client (Files' 100s default)
# times out the whole POST /v1/libraries. Cap it, same pattern the scanner
# uses for every other blocking filesystem call (core.concurrency).
_ADD_PROBE_TIMEOUT_SECONDS = 10.0


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
        replace_file(tmp, self._path)

    def list(self) -> list[Library]:
        return sorted(self._libraries.values(), key=lambda lib: lib.name.lower())

    def get(self, library_id: str) -> Library | None:
        return self._libraries.get(library_id)

    def add(self, path: Path) -> Library:
        # Fast idempotent path: an already-registered folder (the common case
        # when the UI re-scans a known folder) is returned without touching the
        # filesystem at all, so a momentarily-wedged mount can never hang a
        # re-add. Stored paths are already resolved; the UI sends the resolved
        # path back, so this string match hits the hot path.
        raw = str(path)
        for lib in self._libraries.values():
            if lib.path == raw:
                return lib

        def _probe() -> Path | None:
            r = path.expanduser().resolve()
            return r if r.is_dir() else None

        outcome = run_with_timeout(_probe, _ADD_PROBE_TIMEOUT_SECONDS)
        if outcome is TIMED_OUT:
            raise NotADirectoryError(f"{path} (unreachable — timed out after {_ADD_PROBE_TIMEOUT_SECONDS:.0f}s)")
        if outcome is None:
            raise NotADirectoryError(str(path))
        root = outcome
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
