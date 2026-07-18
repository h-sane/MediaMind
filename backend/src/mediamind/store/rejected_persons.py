"""Person-scoped "not this person" rejections (see db.py's `_v7_migration`).

Recorded when a user excludes or redirects a specific file out of a person's
review batch (folder-match merge, materialize) so a later rescan/organize
never silently re-files it under that person. Keyed by content_hash rather
than faces.id or files.id, for the same reason `rejected_faces.py` is: both
survive a rename/move, but `faces` rows get deleted and recreated wholesale
on every rescan (persist_face_scan).
"""

from __future__ import annotations

import sqlite3
import time


def reject_person_files(
    conn: sqlite3.Connection, provider_id: str, person_id: int, file_ids: list[int]
) -> None:
    """Mark these files as "not this person" so organize routing skips them."""
    if not file_ids:
        return
    placeholders = ",".join("?" * len(file_ids))
    rows = conn.execute(
        f"SELECT content_hash FROM files WHERE id IN ({placeholders})", file_ids
    ).fetchall()
    now = time.time()
    for r in rows:
        content_hash = r["content_hash"]
        if not content_hash:
            continue  # can't key a durable rejection without a hash
        conn.execute(
            """
            INSERT OR IGNORE INTO rejected_person_files
              (content_hash, provider_id, person_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (content_hash, provider_id, person_id, now),
        )
