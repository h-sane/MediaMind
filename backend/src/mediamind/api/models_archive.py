"""Request models for archive operations (compress/extract).

Split out of `api/models.py` rather than growing it further — that file is
already ~400 lines, at CLAUDE.md's size-smell threshold. Response shapes
reuse the existing `ExecutionReportOut`/`ManifestEntryOut` from `api/models.py`
unchanged (compress/extract report exactly like move/copy/delete do).
"""

from __future__ import annotations

from pydantic import BaseModel


class FsCompressIn(BaseModel):
    paths: list[str]
    dest: str
    dry_run: bool = False


class FsExtractIn(BaseModel):
    zip_path: str
    dest: str
    dry_run: bool = False
