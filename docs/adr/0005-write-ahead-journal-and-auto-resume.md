# Write-ahead journal + auto-resume for long/interruptible operations

Long-running work — both file-modifying operations (Consolidation, duplicate
deletion) and multi-hour **scans** — is journaled and **automatically resumed**
after any interruption (unmount, crash, force-quit, power loss) on the next
launch, with no manual restart. MediaMind does **not** attempt to prevent a
drive from unmounting.

**Why:** Scans of even 5,000–15,000 files can run many hours and realistically
*will* be interrupted; today they restart from zero, wasting the user's hours
repeatedly. Once the always-on watcher is live, interruption is the normal case,
not an edge case. Preventing unmount is fragile and only guards the
user-initiated case, while a journal recovers from *every* interruption cause
(network drop to Google Drive, sleep, auto-lock, crash, power loss) with one
mechanism.

**Considered and rejected:** holding the volatile drive open to prevent unmount
— fragile, fights the OS, and narrow (doesn't cover crash/power-loss/network).

**Consequences:**
- **File-moving ops** get full ACID semantics: log intent → copy → verify → mark
  done → delete source → mark committed; on replay, committed files are skipped
  and the rest resumed. Copy-then-delete keeps per-file corruption impossible
  regardless of when the interruption lands (the original is never removed until
  the whole copy is verified).
- **Scans** get resumable checkpointing — an *efficiency* guarantee, not a
  corruption one: scanning only reads user files and writes the rebuildable
  index, so it can never corrupt a photo. Interrupted at file 2,000 of 15,000,
  it resumes at 2,001 on next launch with no double-work.
- The existing `oplog.py` is post-hoc undo/redo, not a write-ahead journal — this
  is net-new machinery to build, not a tweak.
