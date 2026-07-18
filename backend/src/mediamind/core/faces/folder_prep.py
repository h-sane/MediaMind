"""Pre-scan structure check for the Faces tool: is the chosen folder a pile of
loose raw files, or already split into named subfolders (likely pre-sorted by
person)? Non-recursive by design — only the library root's own immediate
contents decide whether to recommend corralling loose files into `Unsorted/`;
nested folders are handled by the existing folder-binding detection in
`core/faces/folder_patterns.py`, not here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from mediamind.config import LIBRARY_DATA_DIRNAME
from mediamind.core.scanner import MEDIA_KINDS, kind_of

UNSORTED_DIRNAME = "Unsorted"

MANAGED_DIRNAMES = {"People", UNSORTED_DIRNAME, LIBRARY_DATA_DIRNAME}


@dataclass(frozen=True)
class FolderPrepResult:
    has_subfolders: bool
    top_level_loose_count: int
    named_subfolder_count: int
    already_has_unsorted: bool
    recommend_unsorted: bool


def _scan_top_level(library_root: Path) -> list[os.DirEntry]:
    try:
        return list(os.scandir(library_root))
    except OSError:
        return []


def scan_folder_prep(library_root: Path) -> FolderPrepResult:
    named_subfolder_count = 0
    top_level_loose_count = 0
    already_has_unsorted = False

    for entry in _scan_top_level(library_root):
        if entry.is_dir():
            if entry.name == UNSORTED_DIRNAME:
                already_has_unsorted = True
            if entry.name not in MANAGED_DIRNAMES:
                named_subfolder_count += 1
        elif kind_of(Path(entry.path)) in MEDIA_KINDS:
            top_level_loose_count += 1

    has_subfolders = named_subfolder_count > 0
    return FolderPrepResult(
        has_subfolders=has_subfolders,
        top_level_loose_count=top_level_loose_count,
        named_subfolder_count=named_subfolder_count,
        already_has_unsorted=already_has_unsorted,
        recommend_unsorted=has_subfolders and top_level_loose_count > 0,
    )


def build_unsorted_moves(library_root: Path) -> list[Path]:
    return [
        Path(entry.path)
        for entry in _scan_top_level(library_root)
        if entry.is_file() and kind_of(Path(entry.path)) in MEDIA_KINDS
    ]
