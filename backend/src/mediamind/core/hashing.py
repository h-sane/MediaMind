"""Content hashing for identity and caching.

BLAKE2b (fast, stdlib) identifies file contents. The hash keys the embedding
cache (re-scans skip unchanged files even if renamed/moved) and exact
duplicate detection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB


def hash_file(path: Path) -> str:
    h = hashlib.blake2b(digest_size=32)
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()
