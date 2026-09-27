"""Forget index rows of files that are gone from disk (deleted in review, in Explorer, anywhere).

Only the index changes: a files row goes, and its faces and open review questions go with it
by cascade. Names are keyed by content hash (face_assignments), so a file that comes back
keeps them. Nothing on disk is touched.

One directory listing per indexed folder, not one stat per file: on a network vault that is
2 s instead of 37 s for a 1,000-file library. A folder that can't be listed (drive offline,
unmounted, no permission) is skipped, so an unreachable library never loses its index.
"""

from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from pathlib import Path, PurePosixPath


def forget_missing(conn: sqlite3.Connection, root: Path) -> int:
    """Delete files rows whose file no longer exists under `root`; returns how many."""
    by_folder: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in conn.execute("SELECT id, path FROM files"):
        p = PurePosixPath(r["path"].replace("\\", "/"))
        by_folder[str(p.parent)].append((r["id"], p.name.lower()))

    gone: list[int] = []
    for folder, files in by_folder.items():
        try:
            present = {e.name.lower() for e in os.scandir(root / folder)}
        except FileNotFoundError:
            # The whole folder is gone, but only if the library itself is still there.
            if not root.is_dir():
                continue
            present = set()
        except OSError:
            continue
        gone += [fid for fid, name in files if name not in present]

    if gone:
        conn.executemany("DELETE FROM files WHERE id = ?", [(fid,) for fid in gone])
        conn.commit()
    return len(gone)
