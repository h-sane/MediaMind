"""Request/response models for `GET /v1/fs/search` (Phase I).

Kept out of `api/models.py` deliberately — that module is already at this
project's size-smell threshold and is being left untouched on purpose so a
parallel phase's edits there don't collide with this one. Imported into
`api/routes/fs.py`.
"""

from __future__ import annotations

from pydantic import BaseModel


class SearchResultOut(BaseModel):
    kind: str                  # "folder" | "file"
    name: str
    path: str                  # absolute
    media_kind: str | None     # "image" | "gif" | "video" | "audio"; None for folders
    size: int | None           # None for folders
    mtime: float


class SearchResponseOut(BaseModel):
    path: str                       # the root that was searched
    query: str
    results: list[SearchResultOut]
    truncated: bool                 # True if `results` hit the limit — more matches may exist
