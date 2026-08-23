"""Cross-library People aggregation.

`store/global_people.py` is pure DB access for the small app-data-level
identity store; this module is the business logic that combines it with
each registered library's own per-library index (`store/persons.py`) to
answer "what does this global person's media look like, across every
library it's linked in."
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from mediamind.config import library_data_dir
from mediamind.core.libraries import Library, LibraryRegistry
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
