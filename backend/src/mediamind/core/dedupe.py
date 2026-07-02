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

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mediamind.core.hashing import hash_file
from mediamind.core.scanner import KIND_IMAGE, ScannedFile

DEFAULT_NEAR_THRESHOLD = 5  # max pHash hamming distance to call two images "near"


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

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass
class DuplicateGroup:
    files: list[DuplicateFile]
    match: str  # "exact" | "near"


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
) -> list[DuplicateGroup]:
    media = [f for f in files if f.is_media]
    entries: list[DuplicateFile] = []
    phashes: list[object | None] = []

    total = len(media)
    for i, f in enumerate(media, 1):
        try:
            content_hash = hash_file(f.path)
        except OSError:
            continue  # vanished mid-scan; detection is read-only, just skip
        width, height = _image_dimensions(f.path) if f.kind == KIND_IMAGE else (0, 0)
        entries.append(
            DuplicateFile(
                path=f.path, size=f.size, mtime=f.mtime, kind=f.kind,
                content_hash=content_hash, width=width, height=height,
            )
        )
        phashes.append(_perceptual_hash(f.path) if f.kind == KIND_IMAGE else None)
        if progress is not None:
            progress(i, total)
        if should_cancel is not None and should_cancel():
            return []

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
        group_files = [entries[i] for i in idxs]
        _pick_best(group_files)
        match = "near" if any(near_edge[i] for i in idxs) else "exact"
        group_files.sort(key=lambda f: (not f.is_best, str(f.path)))
        groups.append(DuplicateGroup(files=group_files, match=match))

    groups.sort(key=lambda g: str(g.files[0].path))
    return groups
