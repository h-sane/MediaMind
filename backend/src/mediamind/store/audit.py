"""Audit trail for organize actions.

Wraps the `organize_actions` + `manifest_entries` tables so the rest of the
code never writes raw SQL for audit concerns.
"""

from __future__ import annotations

import sqlite3
import time

from mediamind.core.safety import ExecutionReport


def record_action(
    conn: sqlite3.Connection,
    *,
    kind: str,
    manifest_path: str,
    report: ExecutionReport,
    dry_run: bool,
) -> int:
    """Record an executed (or dry-run) organize action and its manifest entries."""
    cur = conn.execute(
        """
        INSERT INTO organize_actions
          (kind, created_at, manifest_path, planned, handled, ok, dry_run, undone)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            kind,
            time.time(),
            manifest_path,
            report.planned,
            report.handled,
            int(report.ok),
            int(dry_run),
        ),
    )
    action_id: int = cur.lastrowid  # type: ignore[assignment]
    for entry in report.entries:
        conn.execute(
            """
            INSERT INTO manifest_entries (action_id, source, action, destination, error)
            VALUES (?, ?, ?, ?, ?)
            """,
            (action_id, entry.source, entry.action, entry.destination, entry.error),
        )
    conn.commit()
    return action_id


def last_undoable(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Return the most recent non-dry-run successful action that hasn't been undone."""
    return conn.execute(
        """
        SELECT * FROM organize_actions
        WHERE undone = 0 AND dry_run = 0 AND ok = 1
        ORDER BY created_at DESC LIMIT 1
        """
    ).fetchone()


def mark_undone(conn: sqlite3.Connection, action_id: int) -> None:
    conn.execute("UPDATE organize_actions SET undone = 1 WHERE id = ?", (action_id,))
    conn.commit()


def list_actions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM organize_actions ORDER BY created_at DESC"
    ).fetchall()
