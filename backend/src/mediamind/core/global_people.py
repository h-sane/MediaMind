"""Cross-library People aggregation.

`store/global_people.py` is pure DB access for the small app-data-level
identity store; this module is the business logic that combines it with
each registered library's own per-library index (`store/persons.py`) to
answer "what does this global person's media look like, across every
library it's linked in."
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from mediamind.config import global_moves_dir, library_data_dir
from mediamind.core.libraries import Library, LibraryRegistry
from mediamind.core.safety import FileOp
from mediamind.core.safety import execute as safety_execute
from mediamind.store import global_people as gp_store
from mediamind.store import persons as persons_store
from mediamind.store.db import library_db_path, open_db


def open_library_db(library: Library) -> sqlite3.Connection:
    return open_db(library_db_path(library_data_dir(Path(library.path))))


def sync_named_persons(gp_conn: sqlite3.Connection, registry: LibraryRegistry) -> None:
    """Ensure every NAMED local person, in every registered library, has a
    global identity — auto-creating a same-name global person the first time
    it's seen unlinked. This is triggered lazily by reading the Global People
    view (see `list_aggregated`), not by a write-hook on the naming/ingest
    path, so `store/persons.py`'s `rename_person` and `core/ingest.py` stay
    untouched. A person already linked (by this sync or by an explicit
    cross-library link, Phase 4) is left alone."""
    for lib in registry.list():
        try:
            conn = open_library_db(lib)
        except (OSError, sqlite3.Error):
            continue
        try:
            scan = persons_store.latest_faces_scan(conn)
            if scan is None:
                continue
            provider_id = json.loads(scan["params"] or "{}").get("provider_id", "")
            rows = conn.execute(
                "SELECT id, name FROM persons WHERE provider_id = ? AND name IS NOT NULL",
                (provider_id,),
            ).fetchall()
            for row in rows:
                if gp_store.global_for_local(gp_conn, lib.id, row["id"]) is not None:
                    continue
                gid = gp_store.create_global_person(gp_conn, row["name"])
                gp_store.link(gp_conn, gid, lib.id, row["id"], provider_id)
        finally:
            conn.close()


def list_aggregated(gp_conn: sqlite3.Connection, registry: LibraryRegistry) -> list[dict]:
    """One entry per global person, with per-library member summaries and a
    total media count. Opens every registered library's DB — cheap at the
    current scale (dozens of libraries/persons); cache the result at the
    route layer with a short TTL rather than optimizing this further."""
    sync_named_persons(gp_conn, registry)

    library_by_id = {lib.id: lib for lib in registry.list()}
    summaries_cache: dict[str, dict[int, persons_store.PersonSummary]] = {}

    def summaries_for(library_id: str) -> dict[int, persons_store.PersonSummary]:
        if library_id in summaries_cache:
            return summaries_cache[library_id]
        result: dict[int, persons_store.PersonSummary] = {}
        lib = library_by_id.get(library_id)
        if lib is not None:
            try:
                conn = open_library_db(lib)
            except (OSError, sqlite3.Error):
                conn = None
            if conn is not None:
                try:
                    scan = persons_store.latest_faces_scan(conn)
                    if scan is not None:
                        provider_id = json.loads(scan["params"] or "{}").get("provider_id", "")
                        for s in persons_store.list_person_summaries(conn, provider_id):
                            result[s.id] = s
                finally:
                    conn.close()
        summaries_cache[library_id] = result
        return result

    out: list[dict] = []
    for gperson in gp_store.list_global_persons(gp_conn):
        members: list[dict] = []
        total_media = 0
        for plink in gp_store.links_for_global(gp_conn, gperson.id):
            lib = library_by_id.get(plink.library_id)
            summary = summaries_for(plink.library_id).get(plink.local_person_id)
            if lib is None or summary is None:
                continue  # library removed or person deleted since linking
            total_media += summary.media_count
            members.append(
                {
                    "library_id": plink.library_id,
                    "library_name": lib.name,
                    "library_path": lib.path,
                    "local_person_id": plink.local_person_id,
                    "provider_id": plink.provider_id,
                    "name": summary.name,
                    "face_count": summary.face_count,
                    "media_count": summary.media_count,
                    "sample_face_ids": summary.sample_face_ids,
                }
            )
        out.append(
            {
                "id": gperson.id,
                "name": gperson.name,
                "primary_location": gperson.primary_location,
                "media_count": total_media,
                "members": members,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Cross-library link suggestions — always a suggestion, never auto-linked
# (Hussain: "even above 90-95% [...] always require my permission" for
# cross-library identity, unlike the confidence-gated auto-classification
# within one library, Phase 5).
# ---------------------------------------------------------------------------

def list_link_suggestions(gp_conn: sqlite3.Connection, registry: LibraryRegistry) -> list[dict]:
    """Pairs of NAMED local persons, in different libraries, whose centroids
    are close enough to plausibly be the same person — most-similar first.
    Restricted to named persons (like the global identities themselves,
    Phase 2) so a suggestion always has two real names to compare, and to
    pairs sharing `provider_id` — embeddings from different face-recognition
    models/providers are not comparable, so cross-provider pairs are silently
    skipped rather than compared."""
    sync_named_persons(gp_conn, registry)
    dismissed = gp_store.dismissed_link_pairs(gp_conn)

    entries: list[dict] = []
    for lib in registry.list():
        try:
            conn = open_library_db(lib)
        except (OSError, sqlite3.Error):
            continue
        try:
            scan = persons_store.latest_faces_scan(conn)
            if scan is None:
                continue
            provider_id = json.loads(scan["params"] or "{}").get("provider_id", "")
            centroids = persons_store.load_person_centroids(conn, provider_id)
            named_rows = conn.execute(
                "SELECT id FROM persons WHERE provider_id = ? AND name IS NOT NULL", (provider_id,)
            ).fetchall()
            named_ids = {r["id"] for r in named_rows}
            for pid, centroid in centroids.items():
                if pid in named_ids:
                    entries.append(
                        {"library_id": lib.id, "local_person_id": pid, "provider_id": provider_id, "centroid": centroid}
                    )
        finally:
            conn.close()

    out: list[dict] = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            if a["library_id"] == b["library_id"] or a["provider_id"] != b["provider_id"]:
                continue
            gid_a = gp_store.global_for_local(gp_conn, a["library_id"], a["local_person_id"])
            gid_b = gp_store.global_for_local(gp_conn, b["library_id"], b["local_person_id"])
            if gid_a is not None and gid_a == gid_b:
                continue  # already the same global identity
            key_a = (a["library_id"], a["local_person_id"])
            key_b = (b["library_id"], b["local_person_id"])
            lo, hi = (key_a, key_b) if key_b >= key_a else (key_b, key_a)
            if (lo[0], lo[1], hi[0], hi[1]) in dismissed:
                continue
            sim = float(np.dot(a["centroid"], b["centroid"]))
            if sim >= persons_store.MERGE_SUGGESTION_MIN_SIM:
                out.append(
                    {
                        "library_id_a": a["library_id"],
                        "local_person_id_a": a["local_person_id"],
                        "library_id_b": b["library_id"],
                        "local_person_id_b": b["local_person_id"],
                        "similarity": sim,
                    }
                )
    out.sort(key=lambda s: s["similarity"], reverse=True)
    return out[: persons_store.MAX_MERGE_SUGGESTIONS]


def list_move_suggestions(gp_conn: sqlite3.Connection, registry: LibraryRegistry) -> list[dict]:
    """Files virtually tagged to a global person with a `primary_location`
    set, whose absolute path isn't already under that location — grouped by
    global person. A live read, not a stored/triggered write: a file
    "becoming tagged" needs no event, the next read just reflects it, and
    the filesystem stays the source of truth. Setting `primary_location`
    (Phase 2/3) never moves anything by itself — this is the read that turns
    it into concrete suggestions for the Suggestions tab (Phase 7) to
    execute, only on explicit confirmation."""
    library_by_id = {lib.id: lib for lib in registry.list()}
    out: list[dict] = []
    for gperson in gp_store.list_global_persons(gp_conn):
        if not gperson.primary_location:
            continue
        primary = Path(gperson.primary_location).resolve()
        dismissed = gp_store.dismissed_move_hashes(gp_conn, gperson.id)

        items: list[dict] = []
        for plink in gp_store.links_for_global(gp_conn, gperson.id):
            lib = library_by_id.get(plink.library_id)
            if lib is None:
                continue
            try:
                conn = open_library_db(lib)
            except (OSError, sqlite3.Error):
                continue
            try:
                for pf in persons_store.files_for_person(conn, plink.local_person_id):
                    if pf.content_hash and pf.content_hash in dismissed:
                        continue
                    abs_path = (Path(lib.path) / pf.path).resolve()
                    try:
                        already_there = abs_path.is_relative_to(primary)
                    except ValueError:
                        already_there = False
                    if already_there:
                        continue
                    items.append(
                        {
                            "library_id": lib.id,
                            "file_id": pf.file_id,
                            "abs_path": str(abs_path),
                            "content_hash": pf.content_hash,
                        }
                    )
            finally:
                conn.close()

        if items:
            out.append(
                {
                    "global_person_id": gperson.id,
                    "global_person_name": gperson.name,
                    "primary_location": gperson.primary_location,
                    "items": items,
                }
            )
    return out


def resolve_link_suggestion(
    gp_conn: sqlite3.Connection,
    library_id_a: str,
    local_person_id_a: int,
    library_id_b: str,
    local_person_id_b: int,
    provider_id: str,
) -> None:
    """Accept a suggestion — always an explicit user action, never automatic.
    Both sides are expected to already have a global identity (every named
    local person gets one lazily via `sync_named_persons`); B's link is
    repointed onto A's global person, and B's now-empty global person (if it
    had no other members) is pruned so accepting a suggestion doesn't leave a
    duplicate single-member identity behind."""
    gid_a = gp_store.global_for_local(gp_conn, library_id_a, local_person_id_a)
    gid_b = gp_store.global_for_local(gp_conn, library_id_b, local_person_id_b)
    if gid_a is None and gid_b is None:
        raise ValueError("Neither local person has a global identity yet")
    if gid_a is None:
        gid_a = gid_b
    if gid_a == gid_b:
        return
    gp_store.link(gp_conn, gid_a, library_id_b, local_person_id_b, provider_id)
    if gid_b is not None and not gp_store.links_for_global(gp_conn, gid_b):
        gp_store.delete_global_person(gp_conn, gid_b)


# ---------------------------------------------------------------------------
# Bulk cross-drive move execution — the only place files under a "primary
# location" story actually move. Reuses core/safety.py's execute()
# unchanged: copy-then-delete, fsync, collision-safe naming, per-file error
# isolation, dry-run, manifest, count check — every CLAUDE.md safety
# invariant, no new safety code here.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MoveRequestItem:
    global_person_id: int
    library_id: str
    file_id: int


@dataclass(frozen=True)
class ResolvedMoveItem:
    global_person_id: int
    library_id: str
    file_id: int
    source_abs: Path
    dest_folder: Path


def move_plan_hash(items: list[ResolvedMoveItem]) -> str:
    """Content hash of a move batch's (library, file, destination) triples,
    order-independent — mirrors `organize_plan.plan_hash`'s reasoning: a
    same-count-but-different-contents drift between preview and execute
    (e.g. a suggestion was dismissed and a different one took its slot)
    should still be caught, not just a count check."""
    triples = sorted((r.library_id, r.file_id, str(r.dest_folder)) for r in items)
    h = hashlib.sha256()
    for library_id, file_id, dest in triples:
        h.update(library_id.encode("utf-8"))
        h.update(b"\0")
        h.update(str(file_id).encode("utf-8"))
        h.update(b"\0")
        h.update(dest.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def resolve_move_items(
    gp_conn: sqlite3.Connection, registry: LibraryRegistry, items: list[MoveRequestItem]
) -> list[ResolvedMoveItem]:
    """Resolve each requested (global_person_id, library_id, file_id) into a
    concrete source path + destination folder. The destination is always
    read server-side from the person's own `primary_location` — never taken
    from client input directly, so a client can't smuggle in an arbitrary
    destination. A file that's vanished since the suggestion was generated
    (already moved/deleted) is skipped, not a hard error — the rest of the
    batch still proceeds."""
    library_by_id = {lib.id: lib for lib in registry.list()}
    person_cache: dict[int, gp_store.GlobalPerson] = {}
    conns: dict[str, sqlite3.Connection] = {}
    resolved: list[ResolvedMoveItem] = []
    try:
        for item in items:
            person = person_cache.get(item.global_person_id)
            if person is None:
                person = gp_store.get_global_person(gp_conn, item.global_person_id)
                if person is None:
                    raise ValueError(f"Unknown global person {item.global_person_id}")
                person_cache[item.global_person_id] = person
            if not person.primary_location:
                raise ValueError(f'"{person.name}" has no primary location set')

            lib = library_by_id.get(item.library_id)
            if lib is None:
                raise ValueError(f"Unknown library {item.library_id}")
            conn = conns.get(item.library_id)
            if conn is None:
                conn = open_library_db(lib)
                conns[item.library_id] = conn

            row = conn.execute("SELECT path FROM files WHERE id = ?", (item.file_id,)).fetchone()
            if row is None:
                continue
            resolved.append(
                ResolvedMoveItem(
                    global_person_id=item.global_person_id,
                    library_id=item.library_id,
                    file_id=item.file_id,
                    source_abs=Path(lib.path) / row["path"],
                    dest_folder=Path(person.primary_location),
                )
            )
    finally:
        for conn in conns.values():
            conn.close()
    return resolved


def execute_move_plan(
    gp_conn: sqlite3.Connection,
    registry: LibraryRegistry,
    items: list[MoveRequestItem],
    *,
    dry_run: bool,
    expected_count: int | None,
    expected_plan_hash: str | None,
    on_progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    resolved = resolve_move_items(gp_conn, registry, items)
    if not resolved:
        raise ValueError("Nothing to move — every requested file was already gone")

    if expected_count is not None and len(resolved) != expected_count:
        raise ValueError(
            f"Plan changed: expected {expected_count} moves but server computed "
            f"{len(resolved)}. Refresh and re-confirm."
        )
    if expected_plan_hash is not None and move_plan_hash(resolved) != expected_plan_hash:
        raise ValueError(
            "Plan contents changed since you confirmed (a suggestion was dismissed or "
            "added) even though the count may match. Refresh and re-confirm."
        )

    ops = [FileOp(source=r.source_abs, dest_folder=r.dest_folder, mode="move") for r in resolved]
    manifest_path = global_moves_dir() / "manifests" / f"{time.strftime('%Y%m%d-%H%M%S')}_global-move.csv"

    report = safety_execute(
        ops, manifest_path=manifest_path, dry_run=dry_run,
        on_progress=on_progress, should_cancel=should_cancel,
    )

    by_person: dict[int, int] = {}
    for r in resolved:
        by_person[r.global_person_id] = by_person.get(r.global_person_id, 0) + 1
    for gid, count in by_person.items():
        person = gp_store.get_global_person(gp_conn, gid)
        gp_store.record_move_action(
            gp_conn, gid,
            dest_folder=str(person.primary_location) if person and person.primary_location else "",
            file_count=count, dry_run=dry_run, manifest_path=str(manifest_path),
            ok_count=report.handled, error_count=len(report.errors),
        )

    if not dry_run:
        # Filesystem is source of truth: the moved file is gone from its
        # source library, so drop its stale `files` row there. If the
        # destination is itself a registered library, its own watcher/ingest
        # picks the arrived file up independently — appearing as an
        # unlinked local cluster there, not auto-relinked to this global
        # identity (a deliberate, safe ceiling: no silent wrong auto-tag).
        moved_sources = {e.source for e in report.entries if e.action == "moved"}
        by_library: dict[str, list[int]] = {}
        for r in resolved:
            if str(r.source_abs) in moved_sources:
                by_library.setdefault(r.library_id, []).append(r.file_id)
        library_by_id = {lib.id: lib for lib in registry.list()}
        for library_id, file_ids in by_library.items():
            lib = library_by_id.get(library_id)
            if lib is None:
                continue
            conn = open_library_db(lib)
            try:
                conn.executemany("DELETE FROM files WHERE id = ?", [(fid,) for fid in file_ids])
                conn.commit()
            finally:
                conn.close()

    return {
        "planned": report.planned,
        "handled": report.handled,
        "ok": report.ok,
        "dry_run": dry_run,
        "manifest_path": str(report.manifest_path) if report.manifest_path else None,
        "entries": [
            {"source": e.source, "action": e.action, "destination": e.destination, "error": e.error}
            for e in report.entries
        ],
        "plan_hash": move_plan_hash(resolved),
    }
