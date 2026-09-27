"""Content hashing for identity and caching.

BLAKE2b (fast, stdlib) identifies file contents. The hash keys the embedding
cache (re-scans skip unchanged files even if renamed/moved) and exact
duplicate detection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB


def hash_bytes(data: bytes) -> str:
    """The same hash as hash_file, for a file already read into memory."""
    return hashlib.blake2b(data, digest_size=32).hexdigest()


def hash_file(path: Path) -> str:
    h = hashlib.blake2b(digest_size=32)
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


# Fingerprinting a multi-GB video byte by byte means downloading all of it from a
# slow or remote drive before a single frame is looked at (the 90 s cap then fails
# it). A sampled fingerprint reads a few slices instead. It identifies a video for
# the face cache; it is NOT proof two files are identical (see SAMPLED_PREFIX).
SAMPLED_MIN_BYTES = 64 * 1024 * 1024
SAMPLED_PREFIX = "s1:"
_SLICE = 1 << 20
_SLICE_POSITIONS = (0.0, 0.25, 0.5, 0.75)


def sampled_hash(path: Path, size: int) -> str:
    """BLAKE2b over the file size plus five 1 MiB slices (start, quarter points,
    end). Prefixed so nothing mistakes it for a whole-file hash."""
    h = hashlib.blake2b(digest_size=32)
    h.update(size.to_bytes(8, "little"))
    offsets = [int(size * f) for f in _SLICE_POSITIONS] + [max(0, size - _SLICE)]
    with open(path, "rb") as fh:
        for off in offsets:
            fh.seek(off)
            h.update(fh.read(_SLICE))
    return SAMPLED_PREFIX + h.hexdigest()


def is_sampled(content_hash: str | None) -> bool:
    return bool(content_hash) and content_hash.startswith(SAMPLED_PREFIX)
