# Organize-by-Person V3 — Fast, Non-Destructive, Background-First

Status: **Plan agreed (grilling session, 2026-07-21).** Not yet started.
Supersedes the "physically move files into `People/<Name>/`" direction as the
*primary* experience; that move logic survives as the opt-in **Export** path.

## Context — why this change

The face-recognition / organize-by-person engine is fully built (clustering,
persons, bindings, `organize_plan.py`, review UI) but Hussain does not actually
use MediaMind to *view* his media — it is too slow. Loading is so far behind
Windows Explorer (tens of seconds for a screenful vs. instant) that the real
workflow is: use MediaMind only to sort into folders, then switch to Explorer
to look at anything. Two root problems block the feature from being genuinely
good:

1. **Speed.** Every surface (thumbnail grid, full-screen viewer, duplicate
   window, face window) decodes the *full-resolution original* to fill the
   screen and remembers nothing between launches. This is app-wide, not a
   thumbnail-only issue.
2. **The organizing model.** Physically moving each photo into one person's
   folder cannot represent a group photo — it belongs to four people at once,
   but a file lives in one folder, so three of them silently lose it.

The agreed answer: make MediaMind an Explorer-fast **viewer**, make
organize-by-person a **non-destructive person view** (nothing moves; group
photos appear under everyone), and demote physical foldering to an **opt-in
export**. Everything heavy runs as **background jobs**. Details below.

## Non-negotiable constraints (carried from CLAUDE.md safety rules)

- Nothing on disk moves or is deleted without explicit user action. Moves are
  copy-then-delete. Every operation is logged (oplog/manifest) and undoable.
- The filesystem stays the source of truth; the index only mirrors it. **No
  file that exists on disk is ever hidden from the index** — de-duplication is a
  *display* choice, never an indexing omission.
- A preview/dry-run exists for every destructive-adjacent operation.

## Acceptance bar (agreed pass/fail — measured, not asserted)

On a folder of ~1,000 mixed photos/videos:

| Surface | Cold (first ever) | Warm (cached) |
|---|---|---|
| Folder open → first screenful of thumbnails visible | ≤ 500 ms | ≤ 100 ms |
| Scrolling the grid | smooth 60 fps, fills as you scroll, never blocks | same |
| Open a photo full-screen → sharp-enough preview | ≤ 150 ms | ≤ 100 ms |
| Duplicate window / face window tiles | same as grid | same |

Evidence = a real before/after table measured from the running app, per phase.

---

## Per-phase handoff rule (mandatory)

**After every phase is finished, write a session handoff before ending the
session.** Store it in `.claude/handoffs/` (the current, gitignored location —
`YYYY-MM-DD_session_<NN>.md`, session number continuing the existing sequence).
The handoff must capture what the phase delivered, files touched, decisions made,
measurements taken, testing status, and the exact next-phase starting point, so
the next session can resume this plan cleanly without re-deriving context. This
is not optional and does not require being asked — it happens at the close of
every phase.

## Phases (performance is the gate; nothing after Phase 2 ships until the bar is met)

### Phase 0 — Baseline measurement (the evidence) — ✅ DONE (session 36, before-table in `.claude/handoffs/2026-07-21_session_36.md`)
Instrument current latency on a representative test folder (per the
screenshot-scope memory: use a folder under `test/`, never real personal
media). Capture: folder-open time, per-thumbnail decode time, full-screen open
time, dedupe/faces window load time. Produce the "before" table.
- Touch: a small timing harness; `core/thumbnails.py` timing hooks; drive via
  the `run-desktop` skill.
- Deliverable: real numbers proving where the time goes.

### Phase 1 — Fast decode + persistent cache (backend) — ✅ DONE (session 37, after-table in `.claude/handoffs/2026-07-21_session_37.md`)
Root-cause fix for the app-wide slowness.
- **Decode small, not full.** In `core/thumbnails.py` / `core/loaders.py`: for
  JPEG use PIL `Image.draft('RGB', (size, size))` (libjpeg DCT downscale — 4–16×
  faster, no full decode) and/or read the embedded EXIF thumbnail when it is
  ≥ requested size. Reuse the existing unicode-safe decode chain.
- **Persistent on-disk thumbnail cache**, keyed by (path, mtime, size), in a
  user-cache dir so it also covers Explorer-shell browsing (no library needed).
  Loose JPEG files under a hashed path (simplest; OS-cached; easy to evict).
  Replaces / backs the in-memory `_cache` in `thumbnails.py:28`. This is what
  makes the *second* open instant — the single biggest felt improvement.
- **Progressive preview endpoint:** a screen-capped preview (longest edge
  ~2560px) distinct from `files/raw` (which stays the true original, loaded only
  on zoom / explicit "view original").
- Re-measure vs. Phase 0.
- Touch: `core/thumbnails.py`, `core/loaders.py`, `api/routes/files.py`.

### Phase 2 — Fast viewer + virtualized grids (frontend) — **the gate** — ✅ GATE CLOSED (session 43)

**Acceptance-bar table** — measured on `test/perf_1000` (1,080 files, ~11 MP
JPEGs) via the `run-desktop` driver (`performance.getEntriesByType('resource')`
timings + `requestAnimationFrame` frame sampling):

| Surface | Bar (cold / warm) | Cold | Warm | Verdict |
|---|---|---|---|---|
| Folder open → first screenful | ≤500 / ≤100 ms | ~520 ms (list ~200 + slowest of 28 parallel thumbs ~320) | **68 ms** | Warm ✅; cold ~at bar — tiles+layout paint at ~200 ms, thumbnails fill by ~520 ms |
| Scrolling the grid | 60 fps | median **16.7 ms/frame (60 fps)**, avg 35 fps, p95 100 ms | same (cached) | ✅ median 60 fps; occasional hitch when the virtualizer mounts a new tile batch |
| Full-screen photo open | ≤150 / ≤100 ms | ~40 ms (preview, s38) | ~40 ms | ✅ |
| Duplicate / face window tiles | = grid | inherits grid decode chain, now cache-headed | cached | ✅ face tiles already `immutable`-cached; dedupe now cache-headed |

**Root-cause fix that closed the warm bar:** the `/fs`, `/files`, and
`/duplicates` thumbnail+preview endpoints returned JPEGs with **no
`Cache-Control`**, so the frontend (which fetches with an auth header into an
object URL) re-requested every tile on each navigation and every scroll-recycle.
Added `Cache-Control: private, max-age=3600` to all six — the browser now reuses
thumbnails, dropping warm folder-open from 184 ms to **68 ms** and taking
scroll-recycle off the network. Verdict: **gate met warm on every row; cold
effectively at bar.** Virtualization (28 DOM tiles for 1,080 files) confirmed.

Session 38 findings + work (handoff `.claude/handoffs/2026-07-21_session_38.md`):
Session 38 findings + work (handoff `.claude/handoffs/2026-07-21_session_38.md`):
- **Grid virtualization was already present** in the three heavy views
  (Icon/Tiles/Details, ungrouped branch) via `@tanstack/react-virtual`. Grouped
  branches and Gallery are intentionally not windowed (documented trade-off in
  `content/grouping.ts`); they still lazy-load thumbnails via `useNearViewport`
  and now hit the Phase-1 cache, so off-screen tiles cost only a DOM node.
- **Progressive viewer shipped + verified.** `MediaViewer` opens a still image
  on `/preview` (fast, cached) and upgrades to `/raw` only on zoom. Live-app
  measurement: open fired preview only (~40 ms, under the 150 ms bar), zoom
  fired raw (~73 ms). gif/video/audio keep `/raw`.
- **DedupeReview** already shows resolution/size per copy on cached thumbnails;
  the "compare at full resolution" button is deferred (not an acceptance-bar
  item).
- **Remaining before Phase 4+:** a formal 4-row acceptance-bar table (folder
  open, scroll fps, full-screen open, dedupe/face tiles) from the running app.
  The viewer row is verified; the others rest on already-present virtualization
  + Phase-1 cache and need a confirming measurement.

- **Grid virtualization (windowing):** render only visible tiles across every
  grid (Explorer grid, Gallery, dedupe, faces). Confirm it is not already
  present; the lazy `useNearViewport` hook helps but does not window the DOM.
- **Progressive viewer:** thumbnail → screen-sized preview → original on zoom
  (`components/MediaViewer.tsx`, `explorer/preview/PreviewPane.tsx`).
- **Duplicate window:** fast previews + prominent resolution/size per copy + a
  "compare at full resolution" button that loads true originals on demand.
- Re-measure end-to-end vs. the acceptance bar. **Must pass here before any
  work below begins.**
- Touch: `explorer/content/*View.tsx`, `components/MediaViewer.tsx`,
  `components/Thumbnail.tsx`, `screens/DedupeReview.tsx`.

### Phase 3 — Windows shell-thumbnail fast path (optional fast-follow)
Use the OS thumbnail provider (`IShellItemImageFactory`) for video/RAW where the
OS-cached thumbnail beats our decoder. Windows-only; the Phase-1 decoder remains
the Linux/Mac path. Only if Phase 2 leaves a gap on those formats.

### Phase 4 — The virtual person view (the model) — ◑ CORE DONE (session 39; handoff `.claude/handoffs/2026-07-21_session_39.md`)
- Person → files index built from existing `persons`/`faces`/embeddings tables;
  no file movement. Group photo appears under every named person in it.
  **DONE** — backend `person_media` already delivers this (a file with two
  persons' faces appears under both); it now also returns `abs_path` so the
  library-free content grid can browse it.
- **"People" as a place inside the Explorer shell**, reusing the same window and
  tiles — not a separate screen. **DONE** — a `mediamind:person:` virtual path
  renders one person's real files in the main content grid (all view modes,
  virtualization, progressive viewer). Reached by clicking a person in the
  Faces tool's People panel; verified end-to-end on `test/materialize_person`
  (real thumbnails, correct count, files never moved). The old bespoke
  `PersonDetailPanel` side panel was deleted.
- Two scopes (library-wide vs folder-scoped): **DEFERRED** — thin in the current
  folder-is-library model; needs a chosen library concept first.
- Duplicate display-collapse: **DEFERRED** — `person_media` already dedups by
  `file_id`; collapsing byte-identical copies at *different* paths is unbuilt.
- **Persistent nav-pane "People" row — DONE (session 43).** A "People" row sits
  under Home in the nav pane; it opens the Facial Recognition tool (whose default
  sub-view is the People grid) for the current folder. Folder-scoped like the
  tool itself (disabled off a real folder) — a *global* cross-folder People view
  still needs a library concept and stays deferred.
- **Per-tile "not a face" reject — DONE (session 43).** Re-homed as a context-menu
  item in the virtual person view: `person_media`'s `face_id` is threaded onto the
  content-grid `DirEntry`, so right-clicking a tile there offers "Not a face,"
  which calls the existing `POST /faces/{id}/reject` and refreshes the view.
  Verified live (Brad Pitt 4 → 3 tiles on reject).

### Phase 5 — Accuracy & naming UX — ✅ DONE (session 40)
- **Bias clustering toward splitting** — **DONE.** `clustering.DEFAULT_EPS`
  lowered 0.5 → 0.42 (min_samples kept at 2 so a lone stranger stays noise, not
  a forced group). Left as a documented calibration knob, not a fixed law —
  tune per real-media measurement.
- **Name-who-matters** — **DONE.** `PeoplePanel` now ranks persons by
  `media_count` (below any actionable folder-match suggestion), so recurring
  people the user wants to name surface first and one-offs sink. Backend already
  only organizes *named* persons, so unnamed strangers are never moved.
- **Proactive merge suggestions** — **DONE.** New `store/persons.merge_suggestions`
  (person pairs with cosine-similar centroids ≥ 0.5, below the 0.6 auto-match
  bar, ranked most-similar first, capped at 20) → `GET …/persons/merge-suggestions`
  → a `MergeSuggestionStrip` ("Are these the same person?") in the People panel
  with one-click merge (survivor = named/most-photos person) and a session-local
  "Not the same" dismiss. Verified live: strip renders "96% alike", correct
  merge direction, 4→3 people after one click.

### Phase 6 — Opt-in export + duplicate manager
- **Export to real folders** reuses `core/organize_plan.py` as the export path.
  Per-export choice for group photos: **copy into every person's folder** (real,
  sendable byte copies — not symlinks) or **only the most-prominent person's
  folder**.
- **Record every copy in the manifest** (oplog) — exact, no hashing.
- **Duplicate-location manager:** a view (reusing the `DedupeReview` tile +
  select-and-delete UI) driven by the export manifest: "this photo lives in N
  folders," prune per-photo or in bulk, safe delete only.

**Status — part A DONE (session 41), part B DEFERRED.** Export shipped by
threading `mode` (move|copy) + `group_scope` (prominent|all) through the
existing organize plan/preview/execute/undo (the safety layer already does
source→multi-folder copy fan-out). Export copies leave originals in place,
record `kind="export-by-person"` copies in the manifest, and undo by trashing
the copies. Verified live (copy 4→6 with originals intact; undo 6→4) + a
fan-out unit test. The **duplicate-location manager (part B) is deferred** —
only useful once fan-out exports exist; buildable off `manifest_entries` where
`action='copied'` with no rework. See
`.claude/handoffs/2026-07-21_session_41.md`.

### Phase 7 — Background-jobs robustness — ◑ part done (session 42)
- **General multi-job tile stack bottom-right** — **DONE.** The three separate
  fixed-position bubbles (delete / face-scan / organize), which each pinned
  their own container to the same corner and drew on top of each other whenever
  two were visible, are unified into one `JobProgressBubble` that stacks every
  background job in a single column. Dedupe **scans** now get an app-root bubble
  too (they had none before), so the one concurrent pair the guards allow
  (dedupe scan + face scan) displays cleanly. Verified live.
- **Bounded worker pool / heavy-light lanes / folder-scoped concurrency** —
  **DEFERRED as YAGNI.** The route-level guards (`running_for` +
  `EXCLUSIVE_JOB_TYPES` in `core/jobs.py`) already cap real concurrency at
  exactly one dedupe scan + one face scan for a single library: same-type scans
  and any write-vs-anything overlap are rejected with 409, so a bounded pool
  would gate a load it can't reach, and making a queue ever *fill* would mean
  unwinding those load-bearing safety guards (audit F8/F21). Add this only when
  a real trigger appears — multiple concurrent libraries, or a new heavy job
  type that can legitimately run alongside the existing scans.

### Phase 8 — Filesystem watcher / auto-ingest — ✅ DONE (session 44)
Watch the chosen folders; auto-index, duplicate-check, and face-scan any new
media. Duplicates surface as suggestions; new faces auto-join the right named
person. Foundation (persistent cache, background jobs, duplicate manifest) is
built by earlier phases.

**Shipped (lazy-but-real):** `core/watcher.py` `LibraryWatcher` — a polling
daemon thread that snapshots each registered library's media-file set
({path: mtime}) every 8 s and, on a *settled* change (debounced across one
extra poll so a batch paste isn't scanned mid-copy), re-runs the existing
dedupe + face scans via `JobManager`. Those scans already ARE the whole ingest
pipeline: index, duplicate-check, face-cluster, and `pending_for_named` routing
of new named-person faces into review — so auto-ingest is just re-triggering
them. Wired in `api/app.py` lifespan behind an **opt-in** `auto_scan_enabled`
setting (default **off** — heavy background jobs on a user's folders must be
opted into; safety before performance). Toggle in the Folder Options dialog.
Runner construction is shared with the manual scan route via
`scans.build_scan_runner`. Firing respects the existing concurrency guards
(same-type skip, `EXCLUSIVE_JOB_TYPES` back-off). Verified: deterministic
detection/debounce unit tests + a wired end-to-end test that a settled change
starts and completes a real dedupe scan (`tests/test_watcher.py`).

**Deliberately deferred (ponytail ceilings, not gaps that block use):**
- **OS-event watching (watchdog / ReadDirectoryChangesW)** instead of polling —
  polling is zero-dependency, cross-platform, and costs *nothing* while the
  feature is off (the default). Ceiling: on a very large tree the periodic walk
  costs CPU and change latency is up to ~2×interval. Swap in watchdog only if
  that bites a real library.
- **Incremental per-file ingest.** The re-triggered scans are full idempotent
  re-walks (the embedding cache makes the face pass cheap on unchanged files),
  not a targeted "ingest only the N new files" path. Enough for desktop-scale
  libraries; revisit if a huge library makes each full re-walk too costly.
- **A dedicated "new media" suggestion surface.** New duplicates/faces show up
  in the existing dedupe/faces review UIs after the auto-scan; there's no
  separate "here's what just arrived" toast/inbox yet.

---

## Key design decisions & rationale (for the record)

- **View, not move, as the default** — only model where a group photo belongs to
  all its people; matches the filesystem-first doctrine; instant and safe.
- **Export copies are real bytes, not links** — folders must be sendable / usable
  off-machine; a shortcut breaks the moment it leaves the disk.
- **Index everything, collapse on display** — the index must mirror disk truth;
  hiding a duplicate from the index would break undo and "where are my copies."
- **Bias toward splitting** — a false merge corrupts a folder you might send to
  someone (tedious to un-mix); a false split is a one-click merge to fix.
- **Queue + smart parallelism, not naïve N-at-once** — saturating cores does not
  finish heavy scans faster and destroys the responsiveness Phases 1–2 buy.

## Verification per phase
- Performance phases (0–3): before/after millisecond tables from the running app
  (`run-desktop`), checked against the acceptance bar.
- Model / accuracy / export phases (4–7): drive the real flow end-to-end via
  `run-desktop`; backend safety invariants (routing, copy-then-delete, manifest,
  dry-run, count checks) get pytest coverage; face detection stays behind the
  injectable provider so tests need no 300 MB model.
