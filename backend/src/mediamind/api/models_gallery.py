"""Request/response models for `GET /v1/fs/gallery` (Phase O).

Kept out of `api/models.py` deliberately, same reasoning as
`api/models_search.py` for Phase I: an isolated per-phase models file so
edits here never collide with that shared, larger module.
"""

from __future__ import annotations

from pydantic import BaseModel


class GalleryItemOut(BaseModel):
    name: str
    path: str  # absolute
    media_kind: str  # "image" | "gif" | "video" | "audio"
    size: int
    mtime: float


class GalleryResponseOut(BaseModel):
    path: str                    # the root that was walked
    items: list[GalleryItemOut]  # sorted by mtime, most recent first
    truncated: bool               # True if more media exists than `items` includes
