"""Explorer-style file operations (new folder / rename / move / copy / delete)
for the whole-filesystem browsing shell (`api/routes/fs_ops.py`).

Builds on `core/safety.py`'s V0-ported engine rather than reinventing it —
`ExecutionReport`/`ManifestEntry`/`FileOp`/`execute`/`trash` already give
copy-then-delete semantics, per-file resilience, and manifest writing at file
granularity. This module adds the entry-level orchestration and directory-tree
support real Explorer interactions need: same-volume atomic moves, resilient
recursive tree copy/move, Explorer-style collision naming, and (with
`core/oplog.py`) a bounded undo/redo log.

Safety-rule mapping (see CLAUDE.md):
- Same-volume move -> atomic `os.replace` (cannot leave a half-state on
  crash — a *stronger* guarantee than copy-then-delete for this case).
- Cross-volume move, or a directory move that must be recreated on another
  volume -> copy-then-delete: the source is only removed after every byte of
  the copy has succeeded.
- Rename is non-destructive (nothing is lost, trivially reversible) and is
  exempt from the manifest/count-check machinery; it still gets an op-log
  line so `undo`/`redo` can reverse/replay it.
- Every batch operation writes a manifest and never aborts on a single bad
  file — a failure becomes an `error` entry and the rest of the batch
  continues.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from mediamind.config import fs_ops_dir
from mediamind.core.oplog import append_op_log
from mediamind.core.safety import (
    ExecutionReport,
    ManifestEntry,
    _write_manifest,
    new_manifest_path,
)

_ILLEGAL_NAME_CHARS = re.compile(r'[<>:"/\\|?*]')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class FsOpError(ValueError):
    """A validation failure that should become an HTTP 4xx, not a manifest entry."""


class FsNameCollisionError(FsOpError):
    """A rename/new-folder target name already exists — the route maps this
    to 409 so the frontend keeps the rename editor open, distinct from a
    generic 422 validation failure."""


class FsCopyTreeError(FsOpError):
    """A directory copy (`_copy_tree_resilient`) had per-file failures. Carries
    the granular per-file `ManifestEntry` list so the caller can surface each
    one, on top of this summary exception."""

    def __init__(self, message: str, errors: list[ManifestEntry]):
        super().__init__(message)
        self.errors = errors


# ---------------------------------------------------------------------------
# Name validation / collision naming
# ---------------------------------------------------------------------------

def validate_leaf_name(name: str) -> str:
    """Validate a proposed file/folder name (Windows-first rules). Raises
    FsOpError with a user-facing message if invalid; returns the name unchanged
    otherwise (no silent mutation — callers see exactly what will land on disk)."""
    stripped = name.strip()
    if not stripped:
        raise FsOpError("Name cannot be empty")
    if _ILLEGAL_NAME_CHARS.search(stripped):
        raise FsOpError('Name cannot contain: < > : " / \\ | ? *')
    if stripped != name or name.endswith(" ") or name.endswith("."):
        raise FsOpError("Name cannot end with a space or a period")
    if stripped.split(".")[0].upper() in _RESERVED_NAMES:
        raise FsOpError(f'"{stripped}" is a reserved name')
    return stripped


def explorer_unique_destination(folder: Path, src: Path, same_folder: bool) -> Path:
    """Explorer-style collision-safe destination for `src` inside `folder`.

    Pasting into the *same* folder it came from (a copy of an item beside
    itself) uses Explorer's "name - Copy" / "name - Copy (2)" convention;
    pasting into a different folder that already has a same-named entry uses
    "name (2)" / "name (3)" instead. Directories collide the same way as
    files (no extension to preserve).
    """
    dest = folder / src.name
    if not dest.exists():
        return dest
    stem, suffix = src.stem, src.suffix
    n = 1
    while True:
        if same_folder:
            candidate_name = f"{stem} - Copy{suffix}" if n == 1 else f"{stem} - Copy ({n}){suffix}"
        else:
            candidate_name = f"{stem} ({n + 1}){suffix}"
        candidate = folder / candidate_name
        if not candidate.exists():
            return candidate
        n += 1


def _same_volume(a: Path, b: Path) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


# ---------------------------------------------------------------------------
# New folder
# ---------------------------------------------------------------------------

def new_folder(parent: Path, name: str | None) -> Path:
    if name is None:
        base_name = "New folder"
    else:
        base_name = validate_leaf_name(name)

    dest = parent / base_name
    n = 2
    while dest.exists():
        dest = parent / f"{base_name} ({n})"
        n += 1
    dest.mkdir(parents=False, exist_ok=False)
    append_op_log({"kind": "new_folder", "path": str(dest)})
    return dest


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------

def rename(path: Path, new_name: str) -> Path:
    """Rename `path` in place. Callers must reject symlinks *before* resolving
    to this real path — `resolve_os_path` already follows a symlink to its
    real target, so an `os.path.islink` check here would never fire."""
    validated = validate_leaf_name(new_name)
    dest = path.parent / validated
    if dest.exists():
        raise FsNameCollisionError(f'"{validated}" already exists here')
    os.rename(path, dest)
    append_op_log({"kind": "rename", "old_path": str(path), "new_path": str(dest)})
    return dest


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_entries(paths: list[Path], permanent: bool, dry_run: bool = False) -> ExecutionReport:
    report = ExecutionReport(planned=len(paths))
    deleted: list[dict] = []
    for path in paths:
        try:
            if not path.exists() and not os.path.islink(path):
                raise FileNotFoundError("No longer exists")
            action = "deleted" if permanent else "trashed"
            if dry_run:
                report.entries.append(ManifestEntry(str(path), f"dry-run-{action}", "", ""))
            else:
                if permanent:
                    if path.is_dir() and not os.path.islink(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                else:
                    from send2trash import send2trash

                    send2trash(str(path))
                report.entries.append(ManifestEntry(str(path), action, "", ""))
                deleted.append({"path": str(path), "permanent": permanent})
            report.handled += 1
        except Exception as exc:  # a bad item never aborts the rest of the batch
            entry = ManifestEntry(str(path), "error", "", str(exc))
            report.entries.append(entry)
            report.errors.append(entry)

    manifest_path = new_manifest_path(fs_ops_dir(), "delete")
    _write_manifest(manifest_path, report.entries)
    report.manifest_path = manifest_path
    if deleted:
        # Logged for the "Recent deletions" history panel (Phase P item 4)
        # only — `core/oplog.py::undo_last` deliberately has no case for
        # kind "delete" beyond a friendly "can't be undone here" message.
        # Permanent deletes are genuinely gone (nothing to reverse); trashed
        # items went to the real OS Recycle Bin, and restoring from there
        # programmatically by path is the kind of fragile, hard-to-verify
        # shell automation this project's safety rules steer away from — the
        # panel instead hands the user off to the real, trusted Recycle Bin
        # UI to restore (see `api/routes/fs_ops.py`'s recent-deletions route).
        append_op_log({"kind": "delete", "manifest_path": str(manifest_path), "deletes": deleted})
    return report


# ---------------------------------------------------------------------------
# Move / copy
# ---------------------------------------------------------------------------

def _copy_tree_resilient(src_dir: Path, dst_dir: Path) -> tuple[int, list[ManifestEntry]]:
    """Recursively copy a directory, never aborting on one bad file. Returns
    (files copied, error entries) — the caller decides what to do with the
    source based on whether any errors occurred."""
    copied = 0
    errors: list[ManifestEntry] = []
    for root, dirs, files in os.walk(src_dir):
        rel = Path(root).relative_to(src_dir)
        target_root = dst_dir / rel
        try:
            target_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(ManifestEntry(str(Path(root)), "error", "", str(exc)))
            dirs[:] = []  # can't descend further under an uncreated target
            continue
        for name in files:
            src_file = Path(root) / name
            dst_file = target_root / name
            try:
                shutil.copy2(str(src_file), str(dst_file))
                copied += 1
            except OSError as exc:
                errors.append(ManifestEntry(str(src_file), "error", "", str(exc)))
    return copied, errors


def _reject_if_dest_inside_source(source: Path, dest: Path) -> str | None:
    if dest == source:
        return "Source and destination are the same"
    if source in dest.parents:
        return "Cannot move or copy a folder into itself"
    return None


def move_one(source: Path, dest_folder: Path) -> Path:
    """Physically move `source` into `dest_folder`, using the same
    same-volume-atomic / cross-volume-copy-then-delete rule the public
    `move_entries()` batch loop uses. No manifest/oplog bookkeeping — shared
    by that loop and by `core/oplog.py`'s undo/redo, which only need the raw
    operation."""
    if not source.exists():
        raise FileNotFoundError("No longer exists")
    reject_reason = _reject_if_dest_inside_source(source, dest_folder)
    if reject_reason:
        raise FsOpError(reject_reason)

    target = explorer_unique_destination(dest_folder, source, same_folder=False)
    if _same_volume(source, dest_folder):
        os.replace(str(source), str(target))
    elif source.is_dir() and not os.path.islink(source):
        copied, errors = _copy_tree_resilient(source, target)
        if errors:
            raise FsCopyTreeError(f"{len(errors)} file(s) failed to copy — original left in place", errors)
        shutil.rmtree(source)
    else:
        shutil.copy2(str(source), str(target))
        source.unlink()
    return target


def copy_one(source: Path, dest_folder: Path) -> Path:
    """Physically copy `source` into `dest_folder` — the same-folder-vs-
    different-folder collision-naming rule `copy_entries()` uses, factored out
    so undo/redo's copy-redo path shares it exactly."""
    if not source.exists():
        raise FileNotFoundError("No longer exists")
    reject_reason = _reject_if_dest_inside_source(source, dest_folder)
    if reject_reason:
        raise FsOpError(reject_reason)

    same_folder = source.parent.resolve() == dest_folder.resolve()
    target = explorer_unique_destination(dest_folder, source, same_folder)
    if source.is_dir() and not os.path.islink(source):
        copied, errors = _copy_tree_resilient(source, target)
        if errors:
            raise FsCopyTreeError(f"{len(errors)} file(s) failed to copy", errors)
    else:
        shutil.copy2(str(source), str(target))
    return target


def move_entries(sources: list[Path], dest: Path, dry_run: bool = False) -> ExecutionReport:
    """Move each source into `dest` (see `move_one` for the per-item rule)."""
    report = ExecutionReport(planned=len(sources))
    op_entries: list[dict] = []

    for source in sources:
        try:
            if not source.exists():
                raise FileNotFoundError("No longer exists")
            if dest == source.parent:
                report.entries.append(ManifestEntry(str(source), "unchanged", str(source), ""))
                report.handled += 1
                continue

            if dry_run:
                reject_reason = _reject_if_dest_inside_source(source, dest)
                if reject_reason:
                    raise FsOpError(reject_reason)
                target = explorer_unique_destination(dest, source, same_folder=False)
                report.entries.append(ManifestEntry(str(source), "dry-run-moved", str(target), ""))
                report.handled += 1
                continue

            target = move_one(source, dest)
            report.entries.append(ManifestEntry(str(source), "moved", str(target), ""))
            op_entries.append({"original_parent": str(source.parent), "destination": str(target)})
            report.handled += 1
        except Exception as exc:
            if isinstance(exc, FsCopyTreeError):
                for e in exc.errors:
                    report.entries.append(e)
                    report.errors.append(e)
            entry = ManifestEntry(str(source), "error", "", str(exc))
            report.entries.append(entry)
            report.errors.append(entry)

    manifest_path = new_manifest_path(fs_ops_dir(), "move")
    _write_manifest(manifest_path, report.entries)
    report.manifest_path = manifest_path
    if op_entries and not dry_run:
        append_op_log({"kind": "move", "manifest_path": str(manifest_path), "moves": op_entries})
    return report


def copy_entries(sources: list[Path], dest: Path, dry_run: bool = False) -> ExecutionReport:
    """Copy each source into `dest` (see `copy_one` for the per-item rule)."""
    report = ExecutionReport(planned=len(sources))
    copy_pairs: list[tuple[str, str]] = []

    for source in sources:
        try:
            if not source.exists():
                raise FileNotFoundError("No longer exists")

            if dry_run:
                reject_reason = _reject_if_dest_inside_source(source, dest)
                if reject_reason:
                    raise FsOpError(reject_reason)
                same_folder = source.parent.resolve() == dest.resolve()
                target = explorer_unique_destination(dest, source, same_folder)
                report.entries.append(ManifestEntry(str(source), "dry-run-copied", str(target), ""))
                report.handled += 1
                continue

            target = copy_one(source, dest)
            report.entries.append(ManifestEntry(str(source), "copied", str(target), ""))
            copy_pairs.append((str(source), str(target)))
            report.handled += 1
        except Exception as exc:
            if isinstance(exc, FsCopyTreeError):
                for e in exc.errors:
                    report.entries.append(e)
                    report.errors.append(e)
            entry = ManifestEntry(str(source), "error", "", str(exc))
            report.entries.append(entry)
            report.errors.append(entry)

    manifest_path = new_manifest_path(fs_ops_dir(), "copy")
    _write_manifest(manifest_path, report.entries)
    report.manifest_path = manifest_path
    if copy_pairs and not dry_run:
        append_op_log(
            {
                "kind": "copy",
                "manifest_path": str(manifest_path),
                "copies": [d for _, d in copy_pairs],
                "sources": [s for s, _ in copy_pairs],
            }
        )
    return report


# ---------------------------------------------------------------------------
# Create shortcut (Windows only — see docs/handoffs for the Linux/macOS note)
# ---------------------------------------------------------------------------

def _ps_quote(value: str) -> str:
    """Escape a string for embedding in a single-quoted PowerShell literal.
    Single-quoted PowerShell strings never interpolate `$`/backtick (unlike
    double-quoted ones), so the only escaping needed is doubling an embedded
    `'` — this is what keeps a filename containing `$` or `` ` `` from being
    misinterpreted as PowerShell syntax."""
    return "'" + value.replace("'", "''") + "'"


def create_shortcut(target: Path, dest_folder: Path, name: str | None = None) -> Path:
    """Create a Windows `.lnk` shortcut to `target` inside `dest_folder`, via
    the same WScript.Shell COM object Explorer's own "Create shortcut" uses
    (invoked through PowerShell rather than adding a pywin32 dependency)."""
    if os.name != "nt":
        raise FsOpError("Shortcuts are only supported on Windows")

    base_name = validate_leaf_name(name) if name else f"{target.stem or target.name} - Shortcut"
    dest = dest_folder / f"{base_name}.lnk"
    n = 2
    while dest.exists():
        dest = dest_folder / f"{base_name} ({n}).lnk"
        n += 1

    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(dest))}); "
        f"$s.TargetPath = {_ps_quote(str(target))}; "
        f"$s.WorkingDirectory = {_ps_quote(str(target.parent))}; "
        "$s.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True,
            capture_output=True,
            timeout=15,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise FsOpError(f"Could not create shortcut: {exc}") from exc

    append_op_log({"kind": "create_shortcut", "path": str(dest), "target": str(target)})
    return dest
