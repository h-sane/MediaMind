"""Named people whose faces appear inside a folder.

Powers the Explorer's face-thumbnail folder icons and the Properties "People
in this folder" list: instead of a generic folder glyph, a folder that's been
face-scanned shows the named people detected in the media inside it.

Read-only — resolves which registered library contains the (absolute) folder
path, then reads that library's face index. Never touches the filesystem
beyond the registry lookup, never writes anything.

Recursive: a file counts toward a folder if it lives anywhere in that folder's
subtree, so a parent "Family" folder shows the union of its per-person
subfolders (a group), while a leaf per-person subfolder shows just that person.
Only NAMED persons are shown (unnamed/auto clusters are ignored) — the
deliberate scope decision, so a folder icon is either a recognisable person or
the plain glyph, never a wall of anonymous crops.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from mediamind.core.faces.folder_patterns import FolderFileInfo, load_folder_files
from mediamind.core.libraries import Library, LibraryRegistry
from mediamind.store import persons as persons_store
from mediamind.store.db import open_library_db


@dataclass(frozen=True)
class FolderPerson:
    person_id: int
    name: str
    sample_face_id: int


@dataclass(frozen=True)
class FolderFaces:
    library_id: str
    persons: list[FolderPerson]  # capped, most-files-in-this-folder first
    total_persons: int           # true distinct-named-person count (for the "+N" badge)


# A provider's whole file→person map is one indexed query, but re-running it
# for every visible folder in a directory (30+ on first paint) is wasteful, so
# cache it per library for a few seconds — every folder query for the same
# directory then shares one load. Short TTL, not invalidated on scan/rename:
# folder people change rarely, and a minute of staleness after a rescan is
# harmless (it self-corrects on the next load).
# ponytail: per-library files cache + TTL; batch per-parent-directory if this
# still measures slow at large scale.
_FILES_TTL_SECONDS = 60.0
_files_cache: dict[str, tuple[float, str, list[FolderFileInfo]]] = {}
_cache_lock = threading.Lock()


def _library_for_path(registry: LibraryRegistry, abs_path: Path) -> Library | None:
    for lib in registry.list():
        lib_root = Path(lib.path)
        try:
            if abs_path == lib_root or abs_path.is_relative_to(lib_root):
                return lib
        except ValueError:
            continue
    return None


def _is_under(file_rel: str, folder_rel: str) -> bool:
    """Is a file (library-relative posix path) inside this folder's subtree?"""
    if folder_rel in ("", "."):
        return True  # the library root contains everything
    return file_rel.startswith(folder_rel + "/")


def _open_library_db(lib: Library) -> sqlite3.Connection:
    return open_library_db(Path(lib.path))


def _load_files_cached(lib: Library, conn: sqlite3.Connection, provider_id: str) -> list[FolderFileInfo]:
    now = time.time()
    with _cache_lock:
        cached = _files_cache.get(lib.id)
        if cached is not None and now - cached[0] < _FILES_TTL_SECONDS and cached[1] == provider_id:
            return cached[2]
    files = load_folder_files(conn, provider_id)
    with _cache_lock:
        _files_cache[lib.id] = (now, provider_id, files)
    return files


def invalidate_cache() -> None:
    with _cache_lock:
        _files_cache.clear()


def folder_named_persons(
    registry: LibraryRegistry, abs_path: Path, *, limit: int = 3
) -> FolderFaces | None:
    """Named people detected anywhere inside `abs_path`, ranked by how many of
    the folder's files each appears in. Returns None if the path isn't inside
    any registered library, the library has no face scan, or no named person's
    face is in the folder — in every "None" case the caller falls back to the
    plain folder icon."""
    lib = _library_for_path(registry, abs_path)
    if lib is None:
        return None
    try:
        folder_rel = abs_path.relative_to(Path(lib.path)).as_posix()
    except ValueError:
        return None
    if folder_rel == ".":
        folder_rel = ""

    conn = _open_library_db(lib)
    try:
        scan = persons_store.latest_faces_scan(conn)
        if scan is None:
            return None
        provider_id = json.loads(scan["params"] or "{}").get("provider_id", "")

        files = _load_files_cached(lib, conn, provider_id)
        counts: dict[int, int] = {}
        for f in files:
            if _is_under(f.path, folder_rel):
                for pid in f.person_ids:
                    counts[pid] = counts.get(pid, 0) + 1
        if not counts:
            return None

        summaries = {s.id: s for s in persons_store.list_person_summaries(conn, provider_id)}
    finally:
        conn.close()

    named: list[tuple[int, int, str, int]] = []  # (count, person_id, name, sample_face_id)
    for pid, count in counts.items():
        s = summaries.get(pid)
        if s is None or not s.name or not s.sample_face_ids:
            continue
        named.append((count, pid, s.name, s.sample_face_ids[0]))
    if not named:
        return None

    named.sort(key=lambda t: (-t[0], t[1]))
    persons = [
        FolderPerson(person_id=pid, name=name, sample_face_id=fid)
        for _, pid, name, fid in named[:limit]
    ]
    return FolderFaces(library_id=lib.id, persons=persons, total_persons=len(named))
