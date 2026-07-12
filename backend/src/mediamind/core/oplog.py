"""Op-log storage and undo/redo for Explorer file operations (`core/fsops.py`).

Split out of `fsops.py` (M12 Phase L) for file-size hygiene — the storage
primitives here (`append_op_log`/`_read_op_log`/`_rewrite_op_log`) have no
dependency on `fsops.py`, but `undo_last`/`redo_last` need to reverse/replay
the fs operations `fsops.py` implements, so they import it lazily (inside the
function bodies) to avoid a circular top-level import.

Redo is bounded to the single most recently undone operation: `undo_last`
records which op-log entry it just reversed and the log's length at that
moment; `redo_last` only proceeds if the log hasn't grown since (i.e. no new
user action happened in between) — the same rule any editor's redo stack
uses to go stale the moment a new edit is made.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from mediamind.config import fs_ops_dir


def _oplog_path() -> Path:
    return fs_ops_dir() / "oplog.jsonl"


def _redo_state_path() -> Path:
    return fs_ops_dir() / "redo_state.json"


def append_op_log(entry: dict) -> None:
    entry.setdefault("ts", time.time())
    entry.setdefault("undone", False)
    path = _oplog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _read_op_log() -> list[dict]:
    path = _oplog_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _rewrite_op_log(entries: list[dict]) -> None:
    path = _oplog_path()
    with open(path, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def _read_redo_state() -> dict | None:
    path = _redo_state_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_redo_state(state: dict | None) -> None:
    path = _redo_state_path()
    if state is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


@dataclass
class UndoResult:
    ok: bool
    kind: str | None
    message: str


@dataclass
class RedoResult:
    ok: bool
    kind: str | None
    message: str


def undo_last() -> UndoResult:
    """Reverse the most recent non-undone op-log entry. Callable repeatedly
    to walk further back through history — each call only ever targets one
    step, same as a real editor's Ctrl+Z."""
    from mediamind.core import fsops  # lazy: fsops itself imports append_op_log from here

    entries = _read_op_log()
    idx = None
    for i in range(len(entries) - 1, -1, -1):
        if not entries[i].get("undone"):
            idx = i
            break
    if idx is None:
        return UndoResult(ok=False, kind=None, message="Nothing to undo")

    op = entries[idx]
    kind = op["kind"]
    try:
        if kind == "rename":
            old_path, new_path = Path(op["old_path"]), Path(op["new_path"])
            if not new_path.exists():
                raise fsops.FsOpError("Renamed item no longer exists")
            if old_path.exists():
                raise fsops.FsOpError("Original name is occupied again")
            os.rename(new_path, old_path)
        elif kind == "new_folder":
            folder = Path(op["path"])
            if folder.exists():
                if any(folder.iterdir()):
                    raise fsops.FsOpError("Folder is no longer empty")
                folder.rmdir()
        elif kind == "move":
            errors = []
            for m in op["moves"]:
                dest_path = Path(m["destination"])
                if not dest_path.exists():
                    errors.append(f"{dest_path.name}: no longer exists")
                    continue
                try:
                    fsops.move_one(dest_path, Path(m["original_parent"]))
                except Exception as exc:  # one bad item shouldn't hide the rest
                    errors.append(f"{dest_path.name}: {exc}")
            if errors:
                raise fsops.FsOpError("; ".join(errors))
        elif kind == "copy":
            paths = [Path(p) for p in op["copies"] if Path(p).exists()]
            if paths:
                result = fsops.delete_entries(paths, permanent=False)
                if not result.ok:
                    raise fsops.FsOpError("Some copies could not be removed — see manifest")
        elif kind == "create_shortcut":
            shortcut = Path(op["path"])
            if shortcut.exists():
                shortcut.unlink()
        elif kind == "delete":
            # Deletes are never undoable here (see `core/fsops.py::delete_entries`'s
            # comment) — surfaced as a normal, expected "nothing to undo"
            # outcome rather than falling into the generic "Unknown op kind"
            # branch below, which would otherwise read like an app bug.
            return UndoResult(ok=False, kind=kind, message="Deletions can't be undone here — open the Recycle Bin to restore a trashed file.")
        else:
            raise fsops.FsOpError(f"Unknown op kind: {kind}")
    except Exception as exc:
        return UndoResult(ok=False, kind=kind, message=str(exc))

    # Re-read: some branches above call fsops helpers that touch the
    # filesystem only, not the log (move_one/copy_one/create_shortcut are the
    # raw operations, deliberately not the logging wrappers) — so the log
    # itself hasn't grown, but reloading keeps this resilient if it ever does.
    entries = _read_op_log()
    entries[idx]["undone"] = True
    _rewrite_op_log(entries)
    _write_redo_state({"index": idx, "log_len": len(entries)})
    return UndoResult(ok=True, kind=kind, message="Undone")


def redo_last() -> RedoResult:
    """Re-apply the single most recently undone operation. Invalidated the
    moment any new operation is logged (see module docstring) — checked via
    the op-log's length, not a separate "has anything changed" flag."""
    from mediamind.core import fsops

    state = _read_redo_state()
    if state is None:
        return RedoResult(ok=False, kind=None, message="Nothing to redo")

    entries = _read_op_log()
    idx = state.get("index")
    if (
        idx is None
        or idx >= len(entries)
        or len(entries) != state.get("log_len")
        or not entries[idx].get("undone")
    ):
        _write_redo_state(None)
        return RedoResult(ok=False, kind=None, message="Nothing to redo")

    op = entries[idx]
    kind = op["kind"]
    try:
        if kind == "rename":
            old_path, new_path = Path(op["old_path"]), Path(op["new_path"])
            if new_path.exists():
                raise fsops.FsOpError("Name is occupied again")
            if not old_path.exists():
                raise fsops.FsOpError("Original item no longer exists")
            os.rename(old_path, new_path)
        elif kind == "new_folder":
            folder = Path(op["path"])
            if folder.exists():
                raise fsops.FsOpError("Folder already exists")
            folder.mkdir(parents=False, exist_ok=False)
        elif kind == "move":
            errors = []
            for m in op["moves"]:
                destination = Path(m["destination"])
                current = Path(m["original_parent"]) / destination.name
                if not current.exists():
                    errors.append(f"{destination.name}: no longer exists")
                    continue
                try:
                    fsops.move_one(current, destination.parent)
                except Exception as exc:
                    errors.append(f"{destination.name}: {exc}")
            if errors:
                raise fsops.FsOpError("; ".join(errors))
        elif kind == "copy":
            copies = op.get("copies", [])
            sources = op.get("sources", [])
            if not copies or not sources:
                raise fsops.FsOpError("Not enough information to redo this copy")
            dest_folder = Path(copies[0]).parent
            errors = []
            for src in sources:
                source_path = Path(src)
                if not source_path.exists():
                    errors.append(f"{source_path.name}: no longer exists")
                    continue
                try:
                    fsops.copy_one(source_path, dest_folder)
                except Exception as exc:
                    errors.append(f"{source_path.name}: {exc}")
            if errors:
                raise fsops.FsOpError("; ".join(errors))
        elif kind == "create_shortcut":
            dest_path = Path(op["path"])
            if dest_path.exists():
                raise fsops.FsOpError("Shortcut already exists")
            fsops.create_shortcut(Path(op["target"]), dest_path.parent, name=dest_path.stem)
        else:
            raise fsops.FsOpError(f"Unknown op kind: {kind}")
    except Exception as exc:
        return RedoResult(ok=False, kind=kind, message=str(exc))

    entries = _read_op_log()
    entries[idx]["undone"] = False
    _rewrite_op_log(entries)
    _write_redo_state(None)
    return RedoResult(ok=True, kind=kind, message="Redone")


@dataclass
class DeletionEntry:
    path: str
    permanent: bool
    ts: float


DEFAULT_DELETIONS_LIMIT = 100


def list_deletions(limit: int = DEFAULT_DELETIONS_LIMIT) -> list[DeletionEntry]:
    """Flattens every `kind == "delete"` op-log entry (`core/fsops.py::delete_entries`)
    into one `DeletionEntry` per file, most recent first — the read model
    behind the "Recent deletions" history panel (Phase P item 4). Purely a
    history view: nothing here restores anything (see that module's
    comment for why programmatic Recycle Bin restore-by-path is deliberately
    not attempted); the panel instead offers to open the real Recycle Bin."""
    flattened: list[DeletionEntry] = []
    for entry in reversed(_read_op_log()):
        if entry.get("kind") != "delete":
            continue
        ts = entry.get("ts", 0.0)
        for d in entry.get("deletes", []):
            flattened.append(DeletionEntry(path=d["path"], permanent=d["permanent"], ts=ts))
            if len(flattened) >= limit:
                return flattened
    return flattened
