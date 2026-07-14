"""File-operation machinery with the V0 safety guarantees.

Invariants (see CLAUDE.md — these are non-negotiable):
- Moves are copy-then-delete: a mid-run failure never loses data.
- Destination collisions get unique names; nothing is overwritten.
- Every operation is recorded in a manifest (audit trail).
- dry_run=True changes nothing on disk but produces the full plan/manifest.
- Execution ends with a verifiable count check (report.ok).
- Removals go to the OS recycle bin (send2trash), never hard-deleted.
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class FileOp:
    """A planned operation: deliver `source` into `dest_folder`."""

    source: Path
    dest_folder: Path
    mode: str = "move"  # "move" | "copy"


@dataclass
class ManifestEntry:
    source: str
    action: str  # moved | copied | trashed | error | dry-run-<action>
    destination: str
    error: str = ""


@dataclass
class ExecutionReport:
    planned: int = 0
    handled: int = 0
    entries: list[ManifestEntry] = field(default_factory=list)
    errors: list[ManifestEntry] = field(default_factory=list)
    manifest_path: Path | None = None

    @property
    def ok(self) -> bool:
        """Safety check: every planned operation was handled without error."""
        return self.handled == self.planned and not self.errors


def unique_destination(folder: Path, src: Path) -> Path:
    """Collision-safe destination path inside `folder` (V0 `_uniq`)."""
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / src.name
    n = 1
    while dest.exists():
        dest = folder / f"{src.stem}_{n}{src.suffix}"
        n += 1
    return dest


def _write_manifest(path: Path, entries: list[ManifestEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source", "action", "destination", "error"])
        for e in entries:
            writer.writerow([e.source, e.action, e.destination, e.error])


def execute(
    ops: list[FileOp],
    manifest_path: Path | None = None,
    dry_run: bool = False,
) -> ExecutionReport:
    """Execute delivery operations with copy-then-delete semantics.

    Multiple ops may share a source (e.g. copy to several folders); the
    original is deleted only after ALL its copies succeeded, and only for
    "move" mode. A per-op failure is recorded and never aborts the batch.
    """
    report = ExecutionReport(planned=len(ops))

    # Group by source so move-deletion happens once, after all copies.
    by_source: dict[Path, list[FileOp]] = {}
    for op in ops:
        by_source.setdefault(op.source, []).append(op)

    for source, source_ops in by_source.items():
        all_copied = True
        for op in source_ops:
            action = "moved" if op.mode == "move" else "copied"
            try:
                if dry_run:
                    dest = op.dest_folder / source.name
                    entry = ManifestEntry(str(source), f"dry-run-{action}", str(dest))
                else:
                    dest = unique_destination(op.dest_folder, source)
                    shutil.copy2(str(source), str(dest))
                    entry = ManifestEntry(str(source), action, str(dest))
                report.entries.append(entry)
                report.handled += 1
            except Exception as exc:  # never abort the batch on one bad file
                all_copied = False
                entry = ManifestEntry(str(source), "error", "", error=str(exc))
                report.entries.append(entry)
                report.errors.append(entry)
        # copy-then-delete: originals only removed when every copy succeeded
        if not dry_run and all_copied and any(op.mode == "move" for op in source_ops):
            try:
                source.unlink()
            except OSError as exc:
                entry = ManifestEntry(str(source), "error", "", error=f"copied but not deleted: {exc}")
                report.entries.append(entry)
                report.errors.append(entry)

    if manifest_path is not None:
        _write_manifest(manifest_path, report.entries)
        report.manifest_path = manifest_path
    return report


def is_network_location(path: Path) -> bool:
    """True if `path` lives on a network share (UNC path, mapped network
    drive, or WebDAV/virtual-vault mount like Cryptomator) — locations the
    Windows Recycle Bin fundamentally cannot use, the same way real Explorer
    can only offer "permanently delete" for these paths, never "move to
    Recycle Bin"."""
    text = str(path)
    if text.startswith("\\\\") or text.startswith("//"):
        return True
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        drive = os.path.splitdrive(text)[0]
        if not drive:
            return False
        DRIVE_REMOTE = 4
        return ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\") == DRIVE_REMOTE
    except Exception:
        return False


_RECYCLE_SAFE_FILESYSTEMS = {"NTFS", "REFS", "FAT32", "EXFAT", "FAT", "CDFS"}


def filesystem_name(path: Path) -> str | None:
    """Volume filesystem name (e.g. "NTFS") for `path`'s drive, or None if it
    can't be determined. WinFsp/Dokan-style virtual mounts (encrypted vaults
    like Cryptomator) commonly report a custom filesystem name here even
    though `GetDriveTypeW` calls them DRIVE_FIXED like a normal local disk —
    this is how `recycle_bin_supported` catches them."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        drive = os.path.splitdrive(str(path))[0]
        if not drive:
            return None
        fs_buf = ctypes.create_unicode_buffer(261)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(f"{drive}\\"),
            None, 0, None, None, None,
            fs_buf, ctypes.sizeof(fs_buf) // ctypes.sizeof(ctypes.c_wchar),
        )
        return fs_buf.value if ok else None
    except Exception:
        return None


def recycle_bin_supported(path: Path) -> bool:
    """True only when the Recycle Bin can reliably accept files at `path`.

    Used to decide *before* attempting a delete whether to ask for a normal
    "move to Recycle Bin" confirmation or a "this will be permanently
    deleted" one — replacing a reactive try-then-fallback flow. False for
    network locations (see `is_network_location`) and any filesystem outside
    a known-good allow-list (catches WinFsp/Dokan virtual-vault mounts, which
    report as DRIVE_FIXED but often aren't NTFS). An allow-list rather than
    "NTFS-only" avoids wrongly flagging ordinary FAT32/exFAT removable
    drives, which do support the Recycle Bin. Unknown filesystem names stay
    optimistic (True) — `_friendly_trash_error`'s reactive fallback remains
    the backstop for anything this heuristic misses.
    """
    if is_network_location(path):
        return False
    if sys.platform != "win32":
        return True
    fs = filesystem_name(path)
    if fs is None:
        return True
    return fs.upper() in _RECYCLE_SAFE_FILESYSTEMS


def _friendly_trash_error(path: Path, exc: Exception) -> str:
    """`send2trash`'s Windows backend raises a bare `OSError` wrapping a COM
    HRESULT with little to no human-readable text. On a network/virtual
    drive that failure is not a transient per-file glitch — the Recycle Bin
    API categorically does not work there, exactly like double-clicking
    Delete on the same file in real Explorer would skip the Recycle Bin and
    ask to permanently delete instead. Surface that as an explanation, not
    the raw HRESULT."""
    if is_network_location(path):
        return (
            "This file is on a network or virtual drive — Windows' Recycle Bin "
            "does not support these locations, so it could not be trashed. "
            "The file was not changed."
        )
    return str(exc) or "Could not move this file to the Recycle Bin"


def trash(
    paths: list[Path],
    manifest_path: Path | None = None,
    dry_run: bool = False,
    permanent: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ExecutionReport:
    """Send files to the OS recycle bin (recoverable). Never hard-deletes
    unless `permanent=True` — an explicit, separately-confirmed fallback for
    locations (network/virtual drives) where the Recycle Bin is unavailable.

    `on_progress(handled_plus_errored, total)` is called after each file if
    given — lets a long batch report progress to a background job.
    `should_cancel()` is checked before each file if given — cooperative
    cancellation is safe here since each trash/delete is a single atomic
    operation; whatever hasn't been reached yet is simply left untouched.
    """
    from send2trash import send2trash

    report = ExecutionReport(planned=len(paths))
    for path in paths:
        if should_cancel is not None and should_cancel():
            break
        try:
            if dry_run:
                action = "dry-run-deleted" if permanent else "dry-run-trashed"
                report.entries.append(ManifestEntry(str(path), action, ""))
            elif permanent:
                if path.is_dir() and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                report.entries.append(ManifestEntry(str(path), "deleted", ""))
            else:
                send2trash(str(path))
                report.entries.append(ManifestEntry(str(path), "trashed", ""))
            report.handled += 1
        except Exception as exc:
            message = str(exc) if permanent else _friendly_trash_error(path, exc)
            entry = ManifestEntry(str(path), "error", "", error=message)
            report.entries.append(entry)
            report.errors.append(entry)
        if on_progress is not None:
            on_progress(report.handled + len(report.errors), len(paths))
    if manifest_path is not None:
        _write_manifest(manifest_path, report.entries)
        report.manifest_path = manifest_path
    return report


def new_manifest_path(library_data_dir: Path, kind: str) -> Path:
    """Timestamped manifest location inside a library's .mediamind folder."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return library_data_dir / "manifests" / f"{stamp}_{kind}.csv"
