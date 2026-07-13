"""Duplicate detection: exact (content hash) + near (perceptual hash).

Detection is read-only. Exact matching covers every media kind; perceptual
matching covers images only (PRD F1.2 — videos are byte-exact in V1).
Groups are built with union-find so a file connected by either signal joins
the same group.

Known behavior: perceptually uniform images (e.g. solid colors) hash alike
and will group as near-duplicates — they are visually identical, and the
user always reviews before anything is removed.
"""

from __future__ import annotations

import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mediamind.core.concurrency import TIMED_OUT, run_with_timeout
from mediamind.core.hashing import hash_file
from mediamind.core.scanner import KIND_IMAGE, ScannedFile

logger = logging.getLogger("mediamind.dedupe")

DEFAULT_NEAR_THRESHOLD = 5  # max pHash hamming distance to call two images "near"

# A single stalled read must never freeze the whole scan: nothing else bounds
# one file's I/O time. Seen in practice with cloud-sync placeholder files
# (OneDrive Files-On-Demand, Google Drive streaming) and stalled
# network/encrypted-drive mounts, where a single `open()`/`read()` can block
# indefinitely. 30s is generous for even a large local video on a slow disk
# while still bounding the worst case.
DEFAULT_FILE_TIMEOUT_SECONDS = 30.0

# Hashing is I/O-bound (hash_file releases the GIL during reads; Pillow's
# decode is mostly C), so oversubscribing cores pays off — concurrent reads
# keep the disk's queue busy instead of serializing one file at a time.
_HASH_WORKERS = min(8, (os.cpu_count() or 4) * 2)


@dataclass
class DuplicateFile:
    path: Path
    size: int
    mtime: float
    kind: str
    content_hash: str
    width: int = 0
    height: int = 0
    is_best: bool = False
    # Stable across scans (unlike content_hash, which falls back to a
    # per-scan positional sentinel for unique-size files) — set once a file's
    # final group is known, see find_duplicates(). Used to build a
    # cross-scan group_signature() for the dismissal feature.
    identity: str = ""

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass
class DuplicateGroup:
    files: list[DuplicateFile]
    match: str  # "exact" | "near"


def group_signature(identities: list[str]) -> str:
    """A stable cross-scan fingerprint for a group's exact member set.

    Sorted-multiset (not a set) so a 2-file dismissed group and a 3-file
    group that shares those same two files hash differently — adding a new
    duplicate to a previously-dismissed group must produce a new signature so
    the (now-different) group can resurface.
    """
    return hashlib.sha256("|".join(sorted(identities)).encode("utf-8")).hexdigest()


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _image_dimensions(path: Path) -> tuple[int, int]:
    """Cheap: PIL reads only the header for .size."""
    try:
        from PIL import Image

        with Image.open(str(path)) as im:
            return im.size
    except Exception:
        return (0, 0)


def _perceptual_hash(path: Path):
    try:
        import imagehash
        from PIL import Image

        with Image.open(str(path)) as im:
            return imagehash.phash(im)
    except Exception:
        return None  # undecodable image -> participates in exact matching only


def _pick_best(files: list[DuplicateFile]) -> None:
    """Mark the keeper: most pixels, then largest file, then oldest (PRD F1.4)."""
    best = max(files, key=lambda f: (f.pixels, f.size, -f.mtime))
    for f in files:
        f.is_best = f is best


def find_duplicates(
    files: list[ScannedFile],
    near_threshold: int = DEFAULT_NEAR_THRESHOLD,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    file_timeout_seconds: float = DEFAULT_FILE_TIMEOUT_SECONDS,
) -> list[DuplicateGroup]:
    media = [f for f in files if f.is_media]
    entries: list[DuplicateFile] = []
    phashes: list[object | None] = []

    total = len(media)

    # Two byte-exact duplicates must share the same file size (from stat(),
    # already known from scan_folder — no I/O). A file whose size is unique
    # in the library can never be an exact duplicate of anything, so skip its
    # full content hash entirely — the dominant cost on large/video files.
    size_counts: dict[int, int] = {}
    for f in media:
        size_counts[f.size] = size_counts.get(f.size, 0) + 1

    def _process(f: ScannedFile, needs_hash: bool) -> tuple:
        content_hash = hash_file(f.path) if needs_hash else None
        width, height = _image_dimensions(f.path) if f.kind == KIND_IMAGE else (0, 0)
        phash = _perceptual_hash(f.path) if f.kind == KIND_IMAGE else None
        return content_hash, width, height, phash

    def _task(f: ScannedFile) -> tuple | None:
        # Still wrapped in run_with_timeout so a genuinely stalled read costs
        # a leaked daemon thread, not a pool worker — the pool keeps its full
        # concurrency for the rest of the scan.
        try:
            outcome = run_with_timeout(
                lambda: _process(f, size_counts[f.size] > 1), file_timeout_seconds
            )
        except OSError:
            return None  # vanished mid-scan; detection is read-only, just skip
        if outcome is TIMED_OUT:
            logger.warning(
                "dedupe: skipping %s - timed out after %.0fs reading it (likely a "
                "cloud-sync placeholder or a stalled network/encrypted-drive read)",
                f.path, file_timeout_seconds,
            )
            return None
        return outcome  # type: ignore[return-value]

    # The pool finishes files out of order, so results are written back by
    # each file's position in `media` — entries/phashes below must stay
    # index-aligned. None marks a skipped file (timeout or vanished).
    results: list[tuple | None] = [None] * total
    with ThreadPoolExecutor(max_workers=_HASH_WORKERS) as pool:
        futures = {pool.submit(_task, f): i for i, f in enumerate(media)}
        done = 0
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
            done += 1
            if progress is not None:
                progress(done, total)
            if should_cancel is not None and should_cancel():
                # Unstarted tasks never run; in-flight reads finish on their
                # own (each bounded by file_timeout_seconds), same worst-case
                # wait as the old per-file loop.
                for pending in futures:
                    pending.cancel()
                return []

    for i, f in enumerate(media, 1):
        outcome = results[i - 1]
        if outcome is None:
            continue
        content_hash, width, height, phash = outcome
        if content_hash is None:
            # Per-file sentinel (not a shared ""): guarantees it can never
            # collide with another unhashed file in by_hash below, and always
            # compares unequal to every other hash in the near-edge
            # classifier, so exact/near labeling stays correct.
            content_hash = f"\x00uniq:{i}"

        entries.append(
            DuplicateFile(
                path=f.path, size=f.size, mtime=f.mtime, kind=f.kind,
                content_hash=content_hash, width=width, height=height,
            )
        )
        phashes.append(phash)

    uf = _UnionFind(len(entries))
    near_edge = [False] * len(entries)

    # Exact: same content hash.
    by_hash: dict[str, list[int]] = {}
    for i, e in enumerate(entries):
        by_hash.setdefault(e.content_hash, []).append(i)
    for idxs in by_hash.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)

    # Near: pHash hamming distance within threshold (images only).
    # O(n^2) over hashed images — fine at V1's few-thousand-file target;
    # revisit with BK-tree/ANN if libraries grow (Future Scope).
    hashed = [(i, h) for i, h in enumerate(phashes) if h is not None]
    for a in range(len(hashed)):
        i, hi = hashed[a]
        for b in range(a + 1, len(hashed)):
            j, hj = hashed[b]
            if hi - hj <= near_threshold:
                if entries[i].content_hash != entries[j].content_hash:
                    near_edge[i] = near_edge[j] = True
                uf.union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(len(entries)):
        clusters.setdefault(uf.find(i), []).append(i)

    groups: list[DuplicateGroup] = []
    for idxs in clusters.values():
        if len(idxs) < 2:
            continue
        for i in idxs:
            e = entries[i]
            if e.content_hash.startswith("\x00uniq:"):
                # A sentinel-hash file can only ever join a group via a
                # perceptual-hash edge (its by_hash bucket has size 1), so it
                # is guaranteed to have a real phash here.
                phash = phashes[i]
                e.identity = f"phash:{phash}" if phash is not None else e.content_hash
            else:
                e.identity = e.content_hash
        group_files = [entries[i] for i in idxs]
        _pick_best(group_files)
        match = "near" if any(near_edge[i] for i in idxs) else "exact"
        group_files.sort(key=lambda f: (not f.is_best, str(f.path)))
        groups.append(DuplicateGroup(files=group_files, match=match))

    groups.sort(key=lambda g: str(g.files[0].path))
    return groups
