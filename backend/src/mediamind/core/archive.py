"""Compress-to-ZIP / Extract-All for the Explorer shell (`api/routes/fs_ops.py`),
built on the same safety engine as move/copy/delete rather than a parallel one.

Safety-rule mapping (see CLAUDE.md):
- Compress is additive-only — it never mutates a source. The archive is built
  at `<final-name>.zip.part` and only `os.replace()`d onto the final `.zip`
  name once every member has been attempted, so a crash mid-build can never
  leave a corrupt file at the final path.
- Extract enforces zip-slip confinement: every member's target is resolved
  against the extraction root *before* anything is written, and any member
  whose resolved path would land outside that root is rejected as an `error`
  entry rather than extracted or silently dropped.
- Both use per-file `try/except` — one unreadable source (compress) or one
  malformed/colliding member (extract) becomes an `error` entry in the
  `ExecutionReport`, never aborts the batch.
- Collision-naming reuses the project's own existing helpers rather than a
  third naming scheme: `fsops.explorer_unique_destination` for the output
  `.zip` name (Explorer's "name (2).zip" convention — the archive's *name* is
  the thing colliding, exactly the case that helper already handles), and
  `safety.unique_destination` for extracted members landing on an existing
  file (the exact case that helper was written for: placing a same-named
  file inside a folder that already has one).
- `pathsafe.resolve_os_path` cannot be called on a zip member's target
  directly: it requires the path to already exist, which is never true for
  a file extraction is about to create. Confinement is instead checked with
  the same primitive `resolve_os_path` itself uses (`Path.resolve()`,
  non-strict — resolves `..`/symlinks without requiring the target to
  exist) against the extraction root, which *is* validated (and does exist)
  before `extract()` is ever called.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

from mediamind.config import fs_ops_dir
from mediamind.core.fsops import explorer_unique_destination
from mediamind.core.safety import (
    ExecutionReport,
    ManifestEntry,
    _write_manifest,
    new_manifest_path,
    unique_destination,
)


class ArchiveOpError(ValueError):
    """A per-item failure that should become a manifest `error` entry."""


# ---------------------------------------------------------------------------
# Compress
# ---------------------------------------------------------------------------

def _compress_tree(top: Path, zf: zipfile.ZipFile) -> list[ManifestEntry]:
    """Recursively add every file under `top` to `zf`, never aborting on one
    bad file. Returns the list of per-file error entries (empty on full
    success) — mirrors `fsops._copy_tree_resilient`'s resilience pattern."""
    errors: list[ManifestEntry] = []
    for root, _dirs, files in os.walk(top):
        rel_root = Path(root).relative_to(top.parent)
        for name in files:
            src_file = Path(root) / name
            arcname = str(rel_root / name)
            try:
                zf.write(src_file, arcname=arcname)
            except OSError as exc:
                errors.append(ManifestEntry(str(src_file), "error", "", str(exc)))
    return errors


def compress(paths: list[Path], dest: Path, dry_run: bool = False) -> ExecutionReport:
    """Compress `paths` (files and/or folders) into a new zip archive at
    `dest`. `dest` is the desired full archive path (folder + filename);
    a `.zip` suffix is enforced and a colliding name is Explorer-style
    renamed before anything is written."""
    if dest.suffix.lower() != ".zip":
        dest = dest.parent / f"{dest.name}.zip"
    final_dest = explorer_unique_destination(dest.parent, dest, same_folder=False)

    report = ExecutionReport(planned=len(paths))

    if dry_run:
        for path in paths:
            if not path.exists():
                entry = ManifestEntry(str(path), "error", "", "No longer exists")
                report.entries.append(entry)
                report.errors.append(entry)
                continue
            report.entries.append(ManifestEntry(str(path), "dry-run-archived", str(final_dest)))
            report.handled += 1
    else:
        part_path = final_dest.parent / f"{final_dest.name}.part"
        with zipfile.ZipFile(part_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                try:
                    if not path.exists():
                        raise FileNotFoundError("No longer exists")
                    if path.is_dir():
                        errors = _compress_tree(path, zf)
                        if errors:
                            for e in errors:
                                report.entries.append(e)
                                report.errors.append(e)
                            raise ArchiveOpError(f"{len(errors)} file(s) failed to archive")
                    else:
                        zf.write(path, arcname=path.name)
                    report.entries.append(ManifestEntry(str(path), "archived", str(final_dest)))
                    report.handled += 1
                except Exception as exc:  # one bad source never aborts the archive
                    entry = ManifestEntry(str(path), "error", "", str(exc))
                    report.entries.append(entry)
                    report.errors.append(entry)
        # Atomic: the final `.zip` name only ever appears once every member
        # has been attempted — a crash while building leaves only the
        # `.part` file behind, never a truncated archive at the real name.
        os.replace(str(part_path), str(final_dest))

    manifest_path = new_manifest_path(fs_ops_dir(), "compress")
    _write_manifest(manifest_path, report.entries)
    report.manifest_path = manifest_path
    return report


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def _safe_member_target(root: Path, member_name: str) -> Path | None:
    """Resolve a zip member's target inside `root`, rejecting any path that
    would escape it (zip-slip: `../../etc/passwd`-style member names, or an
    absolute/drive-rooted member name). Returns None to reject."""
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized:
        return None
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None

    candidate = root.joinpath(*parts)
    # `resolve()` is non-strict by default: it normalizes `..`/symlinks
    # without requiring the target to exist yet — exactly what's needed to
    # confine a not-yet-written extraction target, which `resolve_os_path`
    # cannot do (it hard-requires existence).
    resolved = candidate.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        return None
    return resolved


def extract(zip_path: Path, dest: Path, dry_run: bool = False) -> ExecutionReport:
    """Extract every member of `zip_path` into `dest` (created if it doesn't
    exist yet). Every member's target is confined inside `dest` before
    anything is written; a member that would escape becomes an `error` entry
    instead of being extracted or silently skipped."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        report = ExecutionReport(planned=1)
        entry = ManifestEntry(str(zip_path), "error", "", str(exc))
        report.entries.append(entry)
        report.errors.append(entry)
        manifest_path = new_manifest_path(fs_ops_dir(), "extract")
        _write_manifest(manifest_path, report.entries)
        report.manifest_path = manifest_path
        return report

    with zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]  # dir entries carry no bytes
        report = ExecutionReport(planned=len(names))

        if not dry_run:
            dest.mkdir(parents=True, exist_ok=True)

        for name in names:
            try:
                target = _safe_member_target(dest, name)
                if target is None:
                    raise ArchiveOpError("Rejected: member path escapes the extraction folder")

                if target.exists():
                    # Collision-rename, reusing the exact helper `move`/`copy`
                    # use for "place this file inside a folder that already
                    # has one of that name" — the same situation here.
                    target = unique_destination(target.parent, target)

                if dry_run:
                    report.entries.append(ManifestEntry(name, "dry-run-extracted", str(target)))
                    report.handled += 1
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                report.entries.append(ManifestEntry(name, "extracted", str(target)))
                report.handled += 1
            except Exception as exc:  # one bad/malicious member never aborts the extract
                entry = ManifestEntry(name, "error", "", str(exc))
                report.entries.append(entry)
                report.errors.append(entry)

    manifest_path = new_manifest_path(fs_ops_dir(), "extract")
    _write_manifest(manifest_path, report.entries)
    report.manifest_path = manifest_path
    return report
