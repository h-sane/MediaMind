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

### Phase 2 — Fast viewer + virtualized grids (frontend) — **the gate** — ◑ IMPLEMENTATION DONE (session 38); formal full-bar table is the remaining gate step
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
- Also deferred: a persistent nav-pane "People" row (global; entry point is the
  Faces tool for now) and the per-tile "not a face" reject action that lived on
  the deleted side panel (belongs in the review flows / a future context menu).

### Phase 5 — Accuracy & naming UX
- **Bias clustering toward splitting** (tighten `clustering.py` `eps` / raise
  `min_samples`) so a stranger is never folded into a named person.
- **Name-who-matters:** clusters ranked by frequency; user names the recurring
  people; strangers/one-offs stay unnamed and are never organized (backend
  already only organizes named persons).
- **Proactive merge suggestions** ("are these the same person?") + one-click
  merge, making over-splitting cheap to resolve.

### Phase 6 — Opt-in export + duplicate manager
- **Export to real folders** reuses `core/organize_plan.py` as the export path.
  Per-export choice for group photos: **copy into every person's folder** (real,
  sendable byte copies — not symlinks) or **only the most-prominent person's
  folder**.
- **Record every copy in the manifest** (oplog) — exact, no hashing.
- **Duplicate-location manager:** a view (reusing the `DedupeReview` tile +
  select-and-delete UI) driven by the export manifest: "this photo lives in N
  folders," prune per-photo or in bulk, safe delete only.

### Phase 7 — Background-jobs robustness
- Extend `core/jobs.py`: **bounded worker pool** with heavy vs. light lanes
  (few concurrent face scans; more concurrent I/O-bound dedupe/thumbnail work),
  a **queued** state, and **folder-scoped concurrency** (non-overlapping folders
  scan in parallel; overlapping ones serialize).
- **General multi-job tile stack bottom-right** for all job types (extend the
  existing bulk-delete bubble), each with live progress + cancel.

### Phase 8 — Filesystem watcher / auto-ingest (later; the north star)
Watch the chosen folders; auto-index, duplicate-check, and face-scan any new
media. Duplicates surface as suggestions; new faces auto-join the right named
person. Foundation (persistent cache, background jobs, duplicate manifest) is
built by earlier phases.

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
