# Performance & Ingest V4 — Shared Per-File Pipeline, Real FS Events, Incremental Dedupe/Faces, Windowed Gallery

Status: **✅ Phases 1-5 shipped (session 46, 2026-08-15).** Shared ingest
pipeline, incremental dedupe flagging, immediate on-ingest face matching
(review gate preserved), watchdog-based FS events + always-on worker, and
Gallery view virtualization are all implemented, tested (478/478 backend,
typecheck/build clean), and verified live (see
`.claude/handoffs/2026-08-15_session_46.md`). Supersedes the two deferred
ceilings at the bottom of `docs/ORGANIZE_BY_PERSON_V3_PLAN.md` Phase 8
("OS-event watching" and "Incremental per-file ingest") and the
never-virtualized grouped-grid trade-off documented in
`explorer/content/GalleryView.tsx` / `content/grouping.ts`. Remaining:
the duplicate-flag toast/badge UI and `IconGridView`'s grouped-branch
virtualization are deliberate fast-follows, not gaps — see the handoff's
"Pending / next steps."

## Context — one root cause behind three asks

All three requests ("always-on incremental ingest", "immediate on-ingest face matching", "Explorer-grade browse speed") reduce to the same missing primitive: **there is no per-file ingest step**. Today every automatic action re-runs a *whole-folder* walk:

- `api/app.py:_auto_scan` (the watcher's callback) calls `build_scan_runner(...)` (`api/routes/scans.py:157`) — the exact same runners the manual Scan button uses.
- `core/dedupe.py:find_duplicates` rehashes **every file's full contents from scratch** each run (no persisted hash cache; the one optimization is the folder-unique-size skip at `dedupe.py:174`). Near-match is O(n²) over all hashed images (`dedupe.py:265`).
- `core/faces/scan.py:make_face_scan_runner` already has the pattern dedupe lacks — it consults the `embeddings` cache keyed by `content_hash` (`store/embeddings.py:get_cached_faces`) and skips detection for unchanged files — but it still walks the whole folder and re-runs DBSCAN over everything.
- `api/routes/fs.py:thumbnail` (line 264) decodes the source file **inline in the HTTP request** on a cache miss; `GalleryView.tsx` renders a real DOM tile for every file in the recursive date-grouped walk. Together these are the 10–15 s folder-open stalls.

The fix is to build **one per-file ingest function** that indexes, hashes (with a persisted cache), dedupe-checks, face-matches, and pre-warms a thumbnail for a *single* file, then:
1. make the always-on worker call it for just the changed files (incremental), and
2. make the existing full-folder scans call it in a loop (so there is one implementation of "process a file", not three).

Everything else (real FS events, incremental dedupe surfacing, immediate face filing, gallery windowing) hangs off that primitive.

## Non-negotiable constraints (carried from CLAUDE.md — do not design around these)

- Filesystem is the source of truth; DB/caches are rebuildable. The in-memory ingest queue (below) is explicitly rebuildable — losing it on crash just means the next poll/full-scan re-derives the delta.
- **Ingest never moves or deletes a file.** It only writes index rows (`files`, `embeddings`, `faces`, `pending_matches`, and the new `duplicate_flags`) and warms the thumbnail cache. All file mutation stays in the existing user-triggered, manifest-audited export/dedupe-execute paths (`core/organize_plan.py`, `store/audit.py`). This is what makes "daemon crashes mid-file" safe: re-ingest is idempotent and touches no user bytes.
- **Review-before-commit is preserved.** "Immediate" means immediate *detection + low-confidence flagging*, never immediate *unreviewed filing*. The existing named-person pending gate (`store/persons.py:persist_face_scan`, `pending_matches` table, `PendingReviewPanel`) stays exactly as-is; incremental ingest routes through the same gate.
- Windows-first: the FS-event mechanism must have a native Windows path (see Phase 2).
- Keep modules ~300–400 lines. New `core/ingest.py` is the one substantial new module; everything else is small edits or thin additions.
- Faces tests stay behind the injectable `FaceProvider` (`providers/base.py`) — no 300 MB model in unit tests. `core/ingest.py` must take a provider factory the same way `make_face_scan_runner` does.

---

## Per-phase handoff rule (mandatory, carried from V3)

After every phase, write a session handoff to `.claude/handoffs/YYYY-MM-DD_session_<NN>.md` (continuing the existing sequence) capturing what shipped, files touched, decisions, measurements, test status, and the exact next-phase start point. Not optional.

---

## Phase 1 — The shared per-file ingest pipeline (architectural core) — ◻ PLANNED

**New file:** `backend/src/mediamind/core/ingest.py` (~250–350 lines).
**Migration:** schema **v10** in `store/db.py` — `ALTER TABLE files ADD COLUMN phash TEXT` (guarded like every other `_vN_migration`).

### The one function both incremental and full paths call

```python
# core/ingest.py
@dataclass
class IngestOutcome:
    file_id: int | None
    content_hash: str | None
    was_cached: bool          # skipped hashing (unchanged file)
    duplicate_of: str | None  # rel-path of an existing matching file, if any
    match_type: str | None    # "exact" | "near"
    new_faces: int
    pending_faces: int        # staged into pending_matches (named-person gate)

def ingest_file(
    conn, library_root, scanned: ScannedFile, *,
    provider: FaceProvider | None,      # None => skip face step (no provider installed)
    provider_id: str | None,
    warm_thumbnail: bool = True,
) -> IngestOutcome:
    rel = scanned.path.relative_to(library_root).as_posix()

    # 1. INDEX + HASH CACHE (reuses files table; adds phash column)
    row = conn.execute("SELECT id,size,mtime,content_hash,phash FROM files WHERE path=?", (rel,)).fetchone()
    unchanged = row and row["size"]==scanned.size and row["mtime"]==scanned.mtime \
                     and row["content_hash"] and (scanned.kind != KIND_IMAGE or row["phash"] is not None)
    if unchanged:
        content_hash, phash = row["content_hash"], row["phash"]; was_cached = True
    else:
        content_hash = hash_file(scanned.path)               # core/hashing.py (blake2b)
        phash = _phash(scanned.path) if scanned.kind==KIND_IMAGE else None  # imagehash.phash, str()
        upsert_file_with_phash(conn, rel, scanned.kind, scanned.size, scanned.mtime, content_hash, phash)
        was_cached = False

    # 2. DEDUPE (cheap, index-driven — NOT O(n²))
    dup, mtype = _find_existing_match(conn, rel, content_hash, phash, scanned.kind)
    if dup:
        flag_duplicate(conn, rel, dup, mtype, content_hash)   # new duplicate_flags table (Phase 3)

    # 3. FACES (cache-first; match-to-existing only, NO DBSCAN — Phase 4)
    new_faces = pending = 0
    if provider_id:
        faces = get_cached_faces(conn, content_hash, provider_id)   # store/embeddings.py
        if faces is None and not was_cached:
            faces = _detect_and_cache(conn, scanned, provider, provider_id)
        new_faces, pending = _match_faces_to_existing_persons(conn, file_id, faces, provider_id)

    # 4. THUMBNAIL PRE-WARM (kills the inline-decode stall — Phase 5)
    if warm_thumbnail and scanned.kind in (KIND_IMAGE, KIND_GIF, KIND_VIDEO):
        media_thumbnail_jpeg(scanned.path, scanned.kind, DEFAULT_GRID_THUMB_SIZE)  # writes L1+L2

    return IngestOutcome(...)

def ingest_path(conn, library_root, abs_path, *, provider=None, provider_id=None, warm_thumbnail=True) -> IngestOutcome:
    """Thin convenience wrapper: stat a single absolute path into a ScannedFile
    and call ingest_file. This is the entry point external callers (the
    always-on worker) use — they never construct ScannedFile themselves."""
```

Helpers `_find_existing_match` and `_match_faces_to_existing_persons` are detailed in Phases 3 and 4. Step 1's `upsert_file_with_phash` extends the existing `store/persons.py:upsert_file` (line 104) with the new `phash` column — modify that function in place (it already `ON CONFLICT(path) DO UPDATE`), add a `phash` param defaulting to `None` so existing callers are unaffected.

### Refactor the two full scans to call `ingest_file`

- `core/faces/scan.py`: its `hash_batch` + `detect_batch` already do steps 1+3 per file. Retarget them to call the shared `ingest_file` (with `warm_thumbnail=False` during a bulk scan to avoid decoding a whole library synchronously — thumbnails warm lazily there). The **DBSCAN cluster-and-persist tail stays** in `scan.py` (it's the new-people-discovery pass; see Phase 4).
- `core/dedupe.py`: `find_duplicates` keeps its group-assembly/union-find/`_pick_best` logic, but sources per-file `content_hash`/`phash`/dimensions from the `files` cache via `ingest_file` step 1 instead of unconditionally rehashing. Unchanged files (`was_cached`) cost a stat + a DB read, not a full file read — this alone makes rescans cheap on large libraries.

**Ponytail note:** this is deliberately *not* a from-scratch "pipeline framework". It is one function plus retargeting two existing loops at it. The full scans keep their own walk + parallel-hash `ThreadPoolExecutor` (`dedupe.py:215`, `scan.py:171`) and their own finalize step (union-find / DBSCAN); only the per-file body is shared. `# ponytail: shared per-file body, not a shared walk/finalize — those two differ (grouping vs clustering) and unifying them buys nothing.`

**Tests:** `tests/test_ingest.py` — cache-hit skips hashing (assert `hash_file` not called on unchanged mtime via a spy), exact-dup flags, phash near-dup flags, face step gated behind injected fake provider. Existing `tests/test_watcher.py`, dedupe, and faces suites must stay green after the refactor.

---

## Phase 2 — Real FS events + always-on incremental worker — ◻ PLANNED (depends on Phase 1)

### FS-event mechanism: add `watchdog`

**Add dependency** to `backend/pyproject.toml`: `"watchdog>=4"`. Justification over the current 8 s poll (`core/watcher.py:34`): `watchdog` uses **`ReadDirectoryChangesW` natively on Windows** (`WindowsApiEmitter`), `inotify` on Linux, `FSEvents` on macOS — one dependency covers the Windows-first + Linux/macOS fallback requirement, and it eliminates the up-to-2×interval latency and periodic full-tree CPU cost flagged as the poll's ceiling. This is the single justified new backend dep in this plan.

**Fallback story (do not delete the poll):** network drives and some virtual filesystems don't emit reliable events; `watchdog` ships `PollingObserver` for exactly this. Keep the existing `LibraryWatcher` poll loop as the `PollingObserver`-equivalent fallback, selected per-library when the native observer fails to schedule (catch `watchdog`'s schedule error → fall back to poll for that root). So: native events for local disks, poll for network mounts.

### Watcher becomes a delta producer, not a full-scan trigger

`core/watcher.py` already snapshots `{path: mtime}` per library. Change `_on_change` to emit the **delta** (`changed = new_paths ∪ mtime_changed_paths`) instead of just "the library changed". With `watchdog`, the delta comes straight from the event (`on_created`/`on_modified`/`on_moved` paths) — no snapshot diff needed on the event path; keep the snapshot-diff only in the poll fallback.

Debounce stays (it solves mid-copy): `watchdog` fires per-write, so a large file still-copying emits many `modified` events. Keep the existing "settle across one extra tick" debounce, keyed per-path, before enqueuing.

### The always-on worker: one global coalescing thread, not a thread-per-file

**New file:** `backend/src/mediamind/core/ingest_worker.py` (~150 lines).

```python
class IngestWorker:
    """One daemon thread for the whole app. Drains a bounded queue of
    (library_id, abs_path) and calls core.ingest.ingest_path per file, in
    batches. Idle (blocked on queue.get) when nothing changes => ~0 CPU/mem."""
    _MAX_QUEUE = 20_000          # backpressure ceiling; drops-with-warn beyond => next full scan catches up
    _BATCH = 64                  # commit/report cadence
    _PROVIDER_IDLE_UNLOAD_S = 300  # unload the 300MB face model after 5 min idle

    def enqueue(self, library_id, paths): ...   # coalesces dupes via a set; respects _MAX_QUEUE
    def _run(self):
        while not self._stop.is_set():
            batch = self._drain_up_to(self._BATCH)          # blocks if empty
            for library_id, group in by_library(batch):
                if self._exclusive_active(library_id):       # see race section below
                    self._requeue(group); continue
                with self._jm.mark_busy(library_id, "ingest"):   # short-lived => manual ops wait <=1 batch
                    conn = open_db(...); provider = self._lazy_provider(library_id)
                    for path in group:
                        ingest_path(conn, library_root, path, provider=provider, provider_id=...)
                    self._broadcast_summary(library_id, group)   # WS: triggered_by="watcher"
            self._maybe_unload_provider()
```

**Why this shape (addresses the memory + bulk-drop asks explicitly):**
- **One thread total**, regardless of library count or file count. A bulk drop of 5,000 files enqueues 5,000 *path strings* (~1 MB), not 5,000 threads. The worker processes them 64 at a time; inside each file, hashing reuses the existing bounded `ThreadPoolExecutor(min(8, cpu*2))`. CPU never pegs beyond that existing bound.
- **Bounded queue** (`_MAX_QUEUE`) is the backpressure. Overflow is logged and dropped — safe because the periodic/manual full scan is the backstop that catches anything the incremental path missed (filesystem is truth).
- **Provider unload on idle** directly answers the product owner's memory concern: the 300 MB InsightFace model is loaded lazily on the first face in a batch and unloaded after 5 min idle, so an always-on watcher on an otherwise-quiet folder holds ~0 extra memory. `# ponytail: idle-unload timer, not a full model-lifecycle manager.`
- Registered in `JobManager` via the existing `mark_busy` context (`core/jobs.py:197`) **only for the duration of a batch**, so `running_for(lib)` sees ingest activity and the "Auto" badge lights, but ingest never holds the library busy between batches.

**Wire-up (integration step — done centrally, not by a subagent, to avoid a shared-file collision):** in `api/app.py:_lifespan`, construct `IngestWorker`, start it, and change `LibraryWatcher`'s callback from `_auto_scan` (full re-scan) to `worker.enqueue(lib.id, delta_paths)`. Keep the `auto_scan_enabled` setting gate (`core/settings.py:18`) — worker only enqueues when opted in. `_auto_scan`'s full-scan behavior can be retired once incremental is proven, but keep a manual "full rescan" route (the existing `POST /scans`) as the backstop.

**Tests:** `tests/test_ingest_worker.py` — enqueue coalesces duplicate paths; batch of N calls `ingest_path` N times; queue overflow drops-with-warn; exclusive-active defers (re-queues) rather than racing. Drive deterministically (inject a fake `ingest_path`), no real watchdog observer in unit tests.

---

## Phase 3 — Incremental duplicate detection + surfacing — ◻ PLANNED (depends on Phase 1; parallel with Phase 4)

### Cheap match, not O(n²)

`_find_existing_match(conn, rel, content_hash, phash, kind)` in `core/ingest.py`:
- **Exact:** `SELECT path FROM files WHERE content_hash=? AND path!=? LIMIT 1` — uses the existing `idx_files_hash` index (`db.py:31`). O(1)-ish.
- **Near (images only):** load candidate phashes once per batch (`SELECT path, phash FROM files WHERE phash IS NOT NULL`) and compare Hamming distance ≤ `DEFAULT_NEAR_THRESHOLD` (reuse `dedupe.DEFAULT_NEAR_THRESHOLD=5`). This is O(new × existing) — with the incremental path, `new` is a handful, so it's cheap where the full-scan O(n²) is not. `# ponytail: linear scan of the phash column; swap for a BK-tree only if a library's image count makes even per-file linear scan bite — same upgrade note dedupe.py:263 already carries.`

### New table + surfacing (schema v10, same migration as Phase 1)

```sql
CREATE TABLE IF NOT EXISTS duplicate_flags (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,              -- the newly-ingested file (rel to root)
    match_path TEXT NOT NULL,        -- existing file it duplicates ("show matching location")
    match_type TEXT NOT NULL,        -- 'exact' | 'near'
    content_hash TEXT,
    flagged_at REAL NOT NULL,
    dismissed INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dup_flags_path ON duplicate_flags(path, match_path);
```

**New store module:** `backend/src/mediamind/store/duplicate_flags.py` — `flag_duplicate()`, `list_flags(conn, include_dismissed=False)`, `dismiss_flag(conn, id)`. Every listing stat-checks both `path` and `match_path` live off disk (same pattern as `store/audit.list_export_copies` — filesystem is truth; a hand-deleted copy silently stops appearing).

**Surfacing without opening the Dedupe tool:**
- **WS:** reuse the existing job-broadcast pipe. When `IngestWorker` finishes a batch that produced flags, broadcast a summary (`triggered_by="watcher"`) — piggyback the exact pattern V3 Phase 8 used for the "New media scanned" toast (`core/jobs.py:53` `triggered_by`, `ScanProgress.tsx` "Auto" badge). Extend the batch-summary payload with `new_duplicates: N`.
- **New routes** in a small `api/routes/duplicate_flags.py` (registered in `api/app.py` alongside the others, done centrally at integration time):
  - `GET /v1/libraries/{id}/duplicate-flags` → live-checked list (path, match_path, match_type).
  - `POST /v1/libraries/{id}/duplicate-flags/{flag_id}/dismiss`.
- **Frontend:** a small badge/toast — "New duplicate: `foo.jpg` matches `2023/foo.jpg`". Reuse the existing `JobProgressBubble`/toast surface (V3 Phase 7). Clicking it deep-links into the existing dedupe tool (`explorer/tools/dedupe/`) filtered to that pair. **No new dedupe UI screen** — the existing tile+select+trash UI already handles resolution; incremental only adds the *notification* + a filtered entry point. `# ponytail: reuse the dedupe tool for resolution; only the "you have new dupes" nudge is new.`

**Safety:** flags are advisory only. Nothing is trashed without the user going through the existing manifest-audited dedupe-execute path.

**Tests:** `tests/test_duplicate_flags.py` — exact + near flagging, live-dropout when a flagged path is deleted, dismiss, unique-index prevents double-flagging the same pair.

---

## Phase 4 — Immediate on-ingest face matching — ◻ PLANNED (depends on Phase 1; parallel with Phase 3)

### The key split: match-to-existing per file (immediate) vs. DBSCAN discovery (batched)

DBSCAN clustering (`core/faces/clustering.py`) is inherently a whole-set operation and cannot run per-file. But per-file matching against **existing person centroids** already exists inside `store/persons.py:persist_face_scan` (lines 268–278: cosine-compare each cluster centroid to each person centroid at `AUTO_MATCH_THRESHOLD=0.6`). Immediate matching reuses that comparison at the *single-face* level, with **no DBSCAN**.

`_match_faces_to_existing_persons(conn, file_id, faces, provider_id)` in `core/ingest.py`:
```python
persons = load_person_centroids(conn, provider_id)         # id -> centroid (persons.py already reads this)
named = named_person_ids(conn, provider_id)                # persons.py already computes this set
for f in faces:
    pid, sim = best_person(f.embedding, persons)           # argmax cosine, threshold 0.6
    if pid is None:
        insert_face(conn, file_id, f, person_id=None)      # unmatched => waits for batch DBSCAN
    elif pid in named:
        insert_face(conn, file_id, f, person_id=None)      # GATE: stage pending_matches (existing logic)
        insert_pending_match(conn, face_id, pid, sim)      # PendingReviewPanel confirms => human gate preserved
    else:                                                   # matched to an existing *unnamed* person
        insert_face(conn, file_id, f, person_id=pid)       # auto-attach (identical to today's unnamed behavior)
        record_assignment(conn, ..., pid, source="cluster")# store/face_assignments.py — durable, survives rescan
```

Extract the pending-vs-attach decision from `persist_face_scan` (lines 377–415) into a shared helper in `store/persons.py` so ingest and the full scan use **one** implementation of the gate — don't fork the logic. This is the ponytail root-cause move: one gate function, two callers.

### What "immediate" changes vs. what stays gated

- **Immediate (new):** detection, embedding, `embeddings`-cache write, and *filing to an already-known person* happen the moment the file lands — no waiting for a manual "Scan faces".
- **Unchanged / still gated:** a match to a **named** person still goes through `pending_matches` → `PendingReviewPanel` → `POST /libraries/{id}/pending/decisions` (a human confirms before the face is finalized to that person). A match to an unnamed person auto-attaches exactly as the full scan does today. **Brand-new-person discovery stays batched:** faces that match nobody are stored `person_id=NULL` and picked up by the next full face scan's DBSCAN pass (`core/faces/scan.py` tail), which forms new `Person_00N` groups. So "immediate" never fabricates a new identity from a single face — it only files to identities that already exist and already have a review gate.

**No new physical folders.** Per the settled decision, ingest writes only DB rows; the virtual person view (`person_media`, V3 Phase 4) already renders these with no file movement. Export stays opt-in via `core/organize_plan.py`.

**Tests:** `tests/test_ingest_faces.py` (injected fake `FaceProvider`) — face matching an existing named person creates a `pending_matches` row and leaves `faces.person_id NULL`; matching an unnamed person auto-attaches + records a durable `face_assignments` row; matching nobody stores `person_id NULL`; a rejected `(content_hash, bbox, person)` is not re-staged (reuse `store/rejected_faces.py`).

---

## Phase 5 — Gallery virtualization + thumbnail pre-warm — ◻ PLANNED (frontend fully parallel with Phases 1–4; pre-warm hook depends on Phase 1)

### Windowed grouped grid (reuse the existing dependency)

`@tanstack/react-virtual` is already installed and already drives the ungrouped grids (`IconGridView.tsx:2,147`). `GalleryView.tsx` (and the grouped branch of `IconGridView`) is the only heavy view still rendering every DOM tile. **No new dependency.**

Modify `app/src/renderer/src/explorer/content/GalleryView.tsx`: flatten the date groups into a single indexed row list and window *that*:
```ts
type Row = { kind: 'header'; label: string; count: number }
          | { kind: 'tiles'; entries: DirEntry[] }   // one grid row (columns-wide slice)
const rows: Row[] = useMemo(() => flattenGroupsToRows(groups, columns), [groups, columns])
const virtualizer = useVirtualizer({
  count: rows.length,
  getScrollElement: () => scrollRef.current,
  estimateSize: (i) => rows[i].kind === 'header' ? HEADER_H : sizeConfig.cellHeight,
  overscan: 4,
})
// render only virtualizer.getVirtualItems(); sticky header handling as today
```
This is the same windowing shape as `IconGridView`'s ungrouped branch (`IconGridView.tsx:189`), extended to a mixed header/tile row list. The `useNearViewport` lazy-thumbnail hook in `FileThumbnail.tsx` stays (it now only fires for the ~1 screenful of mounted tiles). **Extract `flattenGroupsToRows` + the windowed-grouped render into a shared hook/component** and apply it to `IconGridView`'s grouped branch too (same documented smell in `content/grouping.ts`) — but if time-boxed, ship Gallery first (the reported pain) and note IconGridView grouped as the same fix. `# ponytail: one flatten-and-window helper, reused; don't hand-roll a second windowing path.`

### Decouple thumbnail generation from the request cycle

The 10–15 s stall is inline decode in `api/routes/fs.py:thumbnail` (line 264) on cold cache. Two fixes, both leaning on existing machinery:
1. **Windowing (above)** caps cold decodes to the visible tiles (~28) instead of the whole folder — the immediate, highest-leverage win.
2. **Pre-warm via the ingest pipeline** — `ingest_file` step 4 already calls `media_thumbnail_jpeg(path, DEFAULT_GRID_THUMB_SIZE)`, which writes both cache tiers (`core/thumbnails.py` L1 + L2 `_disk_put`). So for any **watched** folder, tiles are warm on disk *before* the user ever opens it → folder open hits the warm path.
3. **First-open warm for non-watched folders (fast-follow, not in this pass):** on folder open, enqueue that folder's file paths into `IngestWorker` with a warm-only mode (thumbnail only, skip faces/dedupe) so scrolling pre-generates ahead of the viewport in the background off the request thread. `# ponytail: only if windowing alone doesn't hit the cold bar; measure first.`

**Verification:** measure on a `test/perf_*` folder via the `run-desktop` skill — folder-open → first screenful should feel instant with windowing regardless of folder size; scroll should stay smooth with windowed DOM. Produce a before/after description in the phase handoff.

---

## Sequencing

```
Phase 1 (core/ingest.py + files.phash v10 + refactor scans)   ── must land first
        │
        ├─> Phase 2 (watchdog + IngestWorker)        ─┐
        ├─> Phase 3 (incremental dedupe flags)        │  3 & 4 are disjoint
        └─> Phase 4 (immediate face matching)         ┘  (dedupe tables vs faces tables)
                                                          → parallelizable, separate implementers

Phase 5 (Gallery virtualization)  ── frontend-only, fully parallel from day 1
Phase 5 pre-warm hook             ── trivial, after Phase 1
```

Execution note (session of 2026-08-15): Phase 1+3+4's `core/ingest.py` work was combined into a single implementer to avoid a same-file collision (all three touch `core/ingest.py`'s internals and are tightly coupled — dedupe matching writes `duplicate_flags`, defined in the same pass; face matching calls the persons.py gate, extracted in the same pass). Phase 2 and Phase 5 ran as separate parallel implementers against Phase 1's frozen `ingest_path()` signature. Final `api/app.py` wiring (registering the worker + router, swapping the watcher callback) was done centrally rather than by any subagent, to avoid a shared-file collision between the backend-core and worker implementers.

---

## Consolidated schema / API / frontend changes

### DB (single new migration, `_v10_migration` in `store/db.py`, `SCHEMA_VERSION = 10`)
- `ALTER TABLE files ADD COLUMN phash TEXT` (guarded; incremental near-dup cache).
- `CREATE TABLE duplicate_flags (...)` + unique index (Phase 3).
- **No** new table for the ingest queue — it is in-memory and rebuildable (documented ceiling).

### New backend files
- `core/ingest.py` — the shared per-file pipeline (Phase 1) + `_find_existing_match` (Phase 3) + `_match_faces_to_existing_persons` (Phase 4).
- `core/ingest_worker.py` — the single always-on coalescing worker (Phase 2).
- `store/duplicate_flags.py` — flag persistence + live-checked listing (Phase 3).
- `api/routes/duplicate_flags.py` — list + dismiss routes (Phase 3).

### Modified backend files
- `store/db.py` (v10 migration), `store/persons.py` (`upsert_file` gains `phash`; extract shared pending/attach gate; expose centroid/named-person loaders), `store/embeddings.py` (unchanged API, reused).
- `core/dedupe.py` + `core/faces/scan.py` (retarget per-file body at `ingest_file`; keep union-find / DBSCAN finalize).
- `core/watcher.py` (emit deltas; add watchdog observer with poll fallback).
- `api/app.py` (`_lifespan`: construct/start `IngestWorker`; point watcher callback at `worker.enqueue`; register `duplicate_flags` router) — **integration step, done centrally**.
- `backend/pyproject.toml` (`watchdog>=4`).
- `api/routes/fs.py` (optional warm-only enqueue on folder open — fast-follow, not in this pass).

### WS events
- Reuse existing `broadcast_job` + `triggered_by="watcher"` (`core/jobs.py:53`). Extend the batch-completion summary payload with `new_duplicates` / `new_faces_filed`. No new WS channel (piggyback the V3 Phase 7/8 pipe).

### New / changed API routes
- `GET /v1/libraries/{id}/duplicate-flags`, `POST /v1/libraries/{id}/duplicate-flags/{flag_id}/dismiss`.
- Existing `POST /scans` retained as the manual full-rescan backstop; existing `/pending/decisions` unchanged (the face gate).

### Frontend
- `explorer/content/GalleryView.tsx` — windowed grouped grid via `@tanstack/react-virtual` (+ shared `flattenGroupsToRows` helper, ideally reused by `IconGridView.tsx` grouped branch).
- A duplicate-flag toast/badge + filtered deep-link into the existing `explorer/tools/dedupe/` UI (no new resolution screen) — fast-follow once Phase 3 lands.
- Reuse `ScanProgress.tsx` "Auto" badge for incremental ingest activity — fast-follow once Phase 2 lands.

---

## Risks & tradeoffs (called out explicitly)

- **Memory growth of an always-on process.** Mitigated by: one global worker thread (not per-library, not per-file); a bounded path-string queue (`_MAX_QUEUE`, ~1 MB at ceiling, not file contents); and lazy-load + idle-unload of the 300 MB face model. Worst case at rest is one blocked thread. **Residual risk:** the phash near-dup candidate list is loaded per batch — on a library with hundreds of thousands of images this column load grows; ceiling noted, BK-tree is the upgrade path.
- **Correctness under bulk drops (5,000 files at once).** The watcher's existing debounce waits for the copy to settle before enqueuing; the worker processes in 64-file batches with the existing bounded hashing pool — no thread explosion, no CPU peg. Overflow past `_MAX_QUEUE` is dropped-with-warn and recovered by the manual/periodic full scan (filesystem is truth). **Residual risk:** a file still mid-copy that slips past debounce hashes to a transient value → re-ingested correctly on its final `modified` event (idempotent; the `(size,mtime)` cache key changes).
- **Races with manual scans / exports / deletes on the same files.** The worker checks for an active `EXCLUSIVE_JOB_TYPES` job (`core/jobs.py:32` — organize/dedupe-execute/merge/materialize) before each batch and **defers (re-queues)** rather than racing a copy-then-delete move. It marks the library busy via `mark_busy` only for a batch's duration, so a manual scan/export waits at most one batch (seconds) to start, never the whole queue. If a manual dedupe/faces scan is already running, ingest of that concern is redundant but harmless — both call `ingest_file`, which is per-file-committed and cache-idempotent, so the worst case is duplicated work, not corruption. **Residual risk:** a file deleted between enqueue and processing → `ingest_file` sees a missing file → skip (the existing per-file fault isolation in `dedupe.py`/`scan.py` already tolerates vanished files).
- **Daemon crash mid-file.** Ingest writes only index rows and per-file-commits (following `embeddings`/`files` existing per-file commit discipline) and **moves/deletes nothing**. A crash mid-file leaves a partially-written batch; the next poll/full-scan re-derives and re-ingests idempotently (cache makes unchanged files free). No manifest/audit rule is touched because ingest performs no auditable file operation — all such operations remain in the user-triggered, `organize_actions`/`manifest_entries`-audited paths. This is the core safety property: **the always-on path can never break user media or leave a half-done move**, because it never moves anything.
- **watchdog on network drives.** Native events are unreliable there; the retained poll fallback (per-root selection on schedule failure) covers it — documented, not designed around.
- **Refactor risk in Phase 1.** Retargeting `dedupe.py` and `faces/scan.py` at a shared function is the highest-churn change. Mitigation: land `core/ingest.py` with full test coverage first; keep the two scans' walk/finalize intact; require the existing dedupe + faces + watcher suites green before Phase 2 starts.

---

### Critical files for implementation
- `backend/src/mediamind/core/faces/scan.py` (the existing cache-first per-file pattern to generalize into `core/ingest.py`)
- `backend/src/mediamind/core/dedupe.py` (must switch from full rehash to the `files`/phash cache)
- `backend/src/mediamind/store/db.py` (v10 migration: `files.phash` + `duplicate_flags`)
- `backend/src/mediamind/core/watcher.py` + `backend/src/mediamind/api/app.py` (watchdog + IngestWorker wire-up, replacing `_auto_scan`)
- `app/src/renderer/src/explorer/content/GalleryView.tsx` (windowing via already-installed `@tanstack/react-virtual`, mirroring `IconGridView.tsx`)
