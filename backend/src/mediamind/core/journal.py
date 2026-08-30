"""Write-ahead journal + auto-resume for interrupted file-move batches (ADR-0005).

`safety.execute()` already moves files copy-then-delete with an fsync, so no
single file can be corrupted or lost by an interruption. What it lacks is
*resumability*: if the process dies mid-batch (drive unmount, crash, power
loss), the not-yet-moved files are simply forgotten and the user must notice
and re-run the operation. This module records a batch's intended ops off-drive
(app-data) before it starts and deletes that record when `execute()` returns.
A journal file therefore exists **iff a batch started but never finished** — so
on the next launch `resume_pending()` re-runs whatever was left.

Idempotency comes free from copy-then-delete and needs no per-op "committed"
marks on disk: a source that still exists was not moved (safe to redo); a
source that is gone was already moved (skip it). The filesystem is the ledger.

`ponytail:` best-effort fanout — a source copied to *several* destinations that
is interrupted after some copies but before the source is deleted will, on
resume, remake the already-made copies under collision-safe names (a harmless
extra copy, never data loss). Single-destination moves (the common case) are
exact. Upgrade to per-destination journal marks only if multi-dest fanout
becomes common.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger("mediamind.journal")

# Set once at startup by the app lifespan (config.journals_dir()). Left None in
# unit tests and any non-app context, which disables journaling entirely so
# `safety.execute()` stays a pure function there — no surprise writes to
# app-data, no behaviour change for the existing safety tests.
_JOURNAL_DIR: Path | None = None


def configure(journal_dir: Path | None) -> None:
    global _JOURNAL_DIR
    _JOURNAL_DIR = journal_dir


def begin(ops) -> Path | None:
    """Persist a batch's intended ops and return the journal path (None when
    journaling is not configured). `ops` is a list of `safety.FileOp` — only
    its `source`/`dest_folder`/`mode` fields are read (duck-typed to avoid a
    dependency back on safety)."""
    if _JOURNAL_DIR is None or not ops:
        return None
    payload = {
        "ops": [
            {"source": str(op.source), "dest_folder": str(op.dest_folder), "mode": op.mode}
            for op in ops
        ]
    }
    # Best-effort: journaling is a resumability aid, not the safety guarantee
    # (copy-then-delete already prevents data loss). A failure to write it must
    # never abort the move it is meant to protect.
    try:
        _JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        path = _JOURNAL_DIR / f"{uuid.uuid4().hex}.json"
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(str(tmp), str(path))  # atomic publish; a torn write never appears complete
        return path
    except OSError:
        logger.warning("could not write move journal — proceeding without resume protection", exc_info=True)
        return None


def finish(journal_path: Path | None) -> None:
    """Delete a completed batch's journal. Called from `execute()`'s finally,
    so it must never raise."""
    if journal_path is None:
        return
    try:
        journal_path.unlink()
    except OSError:
        pass


def resume_pending() -> int:
    """Re-run every leftover journal's still-pending ops. Returns the number of
    journals resumed. Safe to call once at startup; a no-op when the journal
    dir is unset or empty."""
    if _JOURNAL_DIR is None:
        return 0
    # Snapshot first: execute() writes fresh journals for the resumed sub-batch,
    # which we must not pick up in this same pass.
    stale = sorted(_JOURNAL_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not stale:
        return 0

    from mediamind.core.safety import FileOp, execute

    resumed = 0
    for path in stale:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("unreadable journal %s — removing", path.name)
            finish(path)
            continue
        # Only ops whose source still exists remain to be done; a gone source
        # was already moved before the interruption (copy-then-delete).
        ops = [
            FileOp(Path(o["source"]), Path(o["dest_folder"]), o.get("mode", "move"))
            for o in payload.get("ops", [])
            if Path(o["source"]).exists()
        ]
        if ops:
            logger.info("resuming %d file op(s) from interrupted batch %s", len(ops), path.name)
            execute(ops)  # journals+finishes its own resumed batch
        finish(path)
        resumed += 1
    return resumed
