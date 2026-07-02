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
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path


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


def trash(paths: list[Path], manifest_path: Path | None = None, dry_run: bool = False) -> ExecutionReport:
    """Send files to the OS recycle bin (recoverable). Never hard-deletes."""
    from send2trash import send2trash

    report = ExecutionReport(planned=len(paths))
    for path in paths:
        try:
            if dry_run:
                report.entries.append(ManifestEntry(str(path), "dry-run-trashed", ""))
            else:
                send2trash(str(path))
                report.entries.append(ManifestEntry(str(path), "trashed", ""))
            report.handled += 1
        except Exception as exc:
            entry = ManifestEntry(str(path), "error", "", error=str(exc))
            report.entries.append(entry)
            report.errors.append(entry)
    if manifest_path is not None:
        _write_manifest(manifest_path, report.entries)
        report.manifest_path = manifest_path
    return report


def new_manifest_path(library_data_dir: Path, kind: str) -> Path:
    """Timestamped manifest location inside a library's .mediamind folder."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return library_data_dir / "manifests" / f"{stamp}_{kind}.csv"
