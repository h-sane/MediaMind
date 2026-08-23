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
