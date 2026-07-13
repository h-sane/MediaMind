# MediaMind — Product Requirements Document (Version 1)

**Status:** Draft for review
**Date:** 2026-07-02
**Scope:** Version 1 only. Everything else is listed in [Future Scope](#10-future-scope) and must not influence V1 design.
**Related docs:** [`../CLAUDE.md`](../CLAUDE.md) (project rules), [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) (how V1 gets built), [`../prototype/HANDOFF.md`](../prototype/HANDOFF.md) (Version 0 prototype context)

> **UI architecture update (2026-07-13):** since this document was written,
> the primary UI layer was redirected to a full Windows Explorer clone (see
> `CLAUDE.md`'s Current State and `docs/USER_GUIDE.md`) rather than the
> library/scan-select flow implied below. This does not change any feature
> requirement in this document — duplicate detection, face recognition, and
> the review/naming/matching flows in §5 are still the target feature set —
> it changes *how the user reaches them*: as actions inside the Explorer
> shell rather than a dedicated app screen. That reintegration work has not
> started yet; treat every "user opens/clicks X screen" phrasing below as
> describing the feature's required behavior, not its final UI location.

---

## 1. Vision

MediaMind is an **open-source, AI-powered media manager** for the desktop.

It is **not** another photo gallery. It is **not** a Google Photos replacement.

It is a **filesystem-first** application that understands media and helps users
organize it **safely**. The user chooses real folders on their machine; the
application works directly on those folders. There is no mandatory import step
and no proprietary library. **The filesystem is the source of truth** — anything
MediaMind knows can be seen on disk, and anything MediaMind stores internally
(indexes, embeddings) can be rebuilt by rescanning.

### Product principles

| Principle | Meaning in practice |
|---|---|
| Filesystem first | Real folders, real files. No import, no vault, no hidden library. |
| Local first, offline capable | Everything runs on the user's machine. No account, no network required (except optional model downloads). |
| Safe | No operation can lose or corrupt user media. Deletion always requires explicit confirmation. |
| Transparent | Every automatic decision is visible and reviewable. Every file operation is recorded in an audit trail. |
| Undo-friendly | Organization actions are reversible. |
| Review before commit | AI decisions are suggestions until the user confirms them. |
| Open source | Apache-2.0 code; recognition models are swappable and their licenses are disclosed. |
| Simple | A user who knows nothing about ML can use every feature. |

### What Version 0 already proved

The prototype (`sort_media.py`, see `prototype/HANDOFF.md`) validated the core engine:
InsightFace face detection + embeddings, unsupervised DBSCAN clustering (no
training or tagging), frame sampling for videos/GIFs, HEIC/AVIF decoding, and a
safety model (copy-then-delete moves, manifest, "everything routes somewhere",
count verification) that V1 inherits wholesale. V1 wraps this engine in a
desktop application, adds duplicate detection, and replaces V0's
"copy media into every person's folder" behavior with review-driven
organization.

---

## 2. Target users

- People with large, messy local media collections (camera dumps, WhatsApp
  exports, old phone backups) who want them organized without uploading
  anything to a cloud service.
- Privacy-conscious users who explicitly avoid cloud photo services.
- The V0 author's own use case: replace a painful digiKam workflow (manual face
  training, no automatic foldering) with zero-training clustering that also
  handles videos.

Skill assumption: comfortable installing a desktop app; **no** command-line or
ML knowledge required.

---

## 3. Platforms & media support

- **Platforms:** Windows (first priority), Linux (second), macOS (third).
  Single codebase; features must not be Windows-only without a documented
  reason.
- **Sources (V1):** local folders chosen by the user. (Cloud providers such as
  Google Drive are Future Scope.)
- **Supported media:**
  - Images: JPEG/JFIF, PNG, BMP, WebP, TIFF
  - HEIC / HEIF / AVIF
  - GIFs (animated; analyzed by frame sampling)
  - Videos: mp4, mov, avi, mkv, webm, m4v, 3gp/3g2, mpg/mpeg, wmv, flv, ts,
    mts, m2ts, ogv (analyzed by frame sampling)
  - Audio: mp3, wav, flac, m4a, aac, ogg, wma, opus, aiff. Audio is a
    first-class media type — browsable, searchable, and playable everywhere
    files are listed (Library file browser and the whole-filesystem
    Explorer). It does not yet participate in duplicate detection or face
    clustering, since those pipelines are visual (perceptual hashing, face
    embeddings); audio-specific duplicate detection is Future Scope (§10).
- Files that cannot be decoded are never lost or skipped silently — they are
  reported and routed to a visible holding area (V0 invariant).

---

## 4. Core concepts

- **Library** — a folder the user has chosen and granted MediaMind permission
  to manage. MediaMind operates only inside libraries the user selected.
- **Scan** — an analysis pass over a library (duplicate scan or face scan).
  Scans read media and update the index; they never move or delete files.
- **Person** — a cluster of faces. Starts unnamed (`Person_001`); becomes a
  **known identity** once the user names it.
- **Review queue** — the staging area where every automatic suggestion waits
  for user confirmation. Nothing leaves review without a user decision.
- **Organize action** — a confirmed batch of file operations (move/remove),
  executed with the V0 safety machinery (copy-then-delete, manifest, count
  check) and undoable.

---

## 5. Version 1 features

### Feature 1 — Duplicate detection

**Goal:** the user scans a folder and resolves duplicates in a few clicks.

Requirements:

- **F1.1** User selects a library (or subfolder) and starts a duplicate scan.
- **F1.2** Detection covers **exact duplicates** (byte-identical, via content
  hash) and **near duplicates** (same image re-encoded/resized, via perceptual
  hash). Near-duplicate matching applies to images; videos are matched
  byte-exact in V1.
- **F1.3** Results are presented as **duplicate groups** with thumbnails,
  file paths, sizes, dimensions, and modified dates side by side.
- **F1.4** The review UI is extremely simple: per group, the "best" copy
  (largest resolution / largest file, tie-broken by oldest) is pre-selected to
  keep; the user can flip selections with one click, and bulk-apply a rule
  ("keep best in all groups") for the whole scan.
- **F1.5** Removal is a single confirmed action for the whole review. Removed
  files go to the OS recycle bin/trash by default (recoverable), with the
  operation recorded in the manifest. Nothing is removed without the explicit
  confirmation step.
- **F1.6** Scan progress is visible and the scan is cancelable; a canceled
  scan leaves files untouched.

Acceptance criteria:

- Byte-identical files in different subfolders are grouped together.
- A resized JPEG copy of a photo is grouped with its original.
- Declining the confirmation dialog results in zero filesystem changes.
- Every removal appears in the audit trail with source path and action.

### Feature 2 — Face recognition (flagship)

**Goal:** cluster the library by person with zero training, using a
user-selected, downloadable recognition model.

Requirements:

- **F2.1** User starts a face scan on a library. The scan detects faces in
  images, GIFs, and videos (frame sampling, per V0) and clusters them into
  unnamed people.
- **F2.2 Model providers are configurable and downloadable.** MediaMind ships
  with **no bundled model**. A provider catalog lists available models — at
  minimum:
  - **General** — a general-purpose face recognition model
  - **Asian faces** — InsightFace `buffalo_l` (the V0 engine; trained on
    Glint360K, strong on Asian faces)
  - Future community models plug in via the same provider interface.
- **F2.3** Only the model the user selects is downloaded. Downloads are
  checksum-verified and resumable; models are cached locally and work offline
  thereafter.
- **F2.4** Before download, the app displays the model's **license and terms**
  (e.g., `buffalo_l` is non-commercial/research-only) and requires
  acknowledgment.
- **F2.5** The user can switch providers per library. Embeddings from different
  providers are never mixed in one clustering pass; switching providers
  requires re-scanning (embedding cache makes re-runs of the *same* provider
  fast).
- **F2.6** Clustering is unsupervised (DBSCAN over embeddings, per V0) with a
  sensible default; an "advanced" setting exposes grouping strictness
  (V0's `eps`) as a simple slider ("split more ↔ merge more").
- **F2.7** All processing is local. No image, face, or embedding ever leaves
  the machine.

Acceptance criteria:

- A fresh install can complete: pick provider → acknowledge license → download
  → scan → see `Person_001..N` clusters with face thumbnails.
- The same person appearing in a photo and a video lands in one cluster
  (V0's global clustering property).
- Airplane-mode operation works fully once a model is cached.

### Feature 3 — Review before saving (multi-person media)

**Goal:** eliminate V0's behavior of copying a video/photo into every detected
person's folder.

Requirements:

- **F3.1** After a face scan, media containing multiple people is flagged
  and shown in a **review screen**: e.g., *Video A appears under Person A,
  Person B, Person C*.
- **F3.2** The user chooses the single final location for that media (one of
  the people, or "leave in place"). The software ensures **no duplicate copies
  are created** — the other candidates become index references only, not files.
- **F3.3** This review happens **before** any final organization is executed.
- **F3.4** Media assigned to only one person skips this screen but still goes
  through the general organize confirmation (Feature 6).

Acceptance criteria:

- A clip with three detected people results in **one** file on disk after
  organization, in the folder the user chose.
- The other people's association with the clip remains visible in the app
  (index-level), even though there is no file copy.

### Feature 4 — Person naming

**Goal:** turn anonymous clusters into identities.

Requirements:

- **F4.1** New clusters are auto-named `Person_001`, `Person_002`, …
- **F4.2** The user can rename any cluster (e.g., `Person_001` → `John`)
  at any time; renames propagate everywhere (UI, folder names on the next
  organize action, review queues).
- **F4.3** A named cluster becomes a **known identity**: its representative
  embeddings (centroid + exemplars) are persisted for future matching.
- **F4.4** The user can merge two clusters ("these are both John") and split
  a cluster is not required in V1 (workaround: adjust strictness and rescan) —
  merging is the required minimum.

Acceptance criteria:

- Renaming survives app restart and rescans.
- Merging two clusters produces one identity containing both sets of media.

### Feature 5 — Known-people matching with pending confirmation

**Goal:** later scans use existing identities, but never file media
automatically.

Requirements:

- **F5.1** When a scan runs on a library with known identities, new faces are
  first matched against known people (embedding similarity threshold), and
  only unmatched faces go through fresh clustering.
- **F5.2** A match is **never** placed directly into the person's real folder.
  It is staged in a pending review area — presented as **"John (Pending)"** —
  until the user confirms.
- **F5.3** The user confirms or rejects pending matches (individually or in
  bulk). Only confirmed media is moved into the person's real folder, via the
  standard organize action.
- **F5.4** A rejected match returns to the unassigned pool (and can form/join
  another cluster).

Acceptance criteria:

- After naming John and adding new photos of John to the library, a rescan
  shows them under "John (Pending)" — and John's real folder is unchanged until
  confirmation.

### Feature 6 — Temporary review for every automatic decision

**Goal:** trust is earned; nothing is permanent without confirmation.

Requirements:

- **F6.1** Every automatic decision that changes files (dedupe removals,
  person foldering, pending-match filing) passes through a review stage.
- **F6.2** Nothing is permanently moved or removed without user confirmation.
- **F6.3** Every executed organize action is recorded in a per-library
  **audit trail** (manifest: source → action → destination, timestamped).
- **F6.4** The most recent organize action can be **undone** (files restored
  to their prior locations using the manifest).
- **F6.5** Every organize action offers a **preview** (dry-run) showing exactly
  what will happen before execution — the V0 `--dry-run` guarantee, in the UI.

---

## 6. Non-functional requirements

- **Safety (inherited from V0, non-negotiable):** copy-then-delete moves;
  everything routes somewhere; per-file error isolation (one corrupt file never
  aborts a scan); post-action count verification; never delete without explicit
  confirmation. See `CLAUDE.md` → Safety rules.
- **Privacy:** no telemetry in V1; no network traffic except user-initiated
  model downloads.
- **Performance:** CPU-only operation must be practical for libraries of a few
  thousand files; an embedding cache makes re-scans and strictness re-tuning
  fast (no re-detection of unchanged files). GPU is an optional acceleration,
  never a requirement. Tens-of-thousands-scale optimizations are Future Scope.
- **Resilience:** scans are cancelable and resumable; the app never leaves a
  library half-organized (organize actions are batched and verified).
- **UI:** simple and modern; a first-run user should reach their first
  duplicate review or face scan without documentation.
- **Accessibility of failure:** when something can't be processed (bad codec,
  corrupt file), the user is told what and why, and the file is untouched.

---

## 7. Out of scope for Version 1

These must **not** influence V1 design or schedule. Listed for the record; see
Future Scope for where they may land later.

Cloud sync · cloud providers (Google Drive etc.) · mobile apps · object
recognition · OCR · event recognition · scene detection · maps/geo views ·
AI chat · generative AI · image editing · photo editing · timeline view ·
memory generation · anything else unrelated to the V1 goals above.

---

## 8. Success criteria for V1

1. A non-technical Windows user can install MediaMind, point it at a messy
   folder, resolve duplicates, run a face scan, name three people, and end with
   an organized folder tree — without touching a terminal.
2. Zero data-loss reports: every file that existed before an operation exists
   after it (or sits in the recycle bin following an explicit removal).
3. The V0 author retires `sort_media.py` for daily use.
4. At least two face-model providers are installable through the provider
   catalog.

---

## 9. Open questions (to resolve during implementation)

- Which model backs the "General" provider (candidate: an ONNX
  detection+embedding pair with a permissive license, to contrast with
  `buffalo_l`'s non-commercial terms)? Must be resolved before release —
  V1 should ship with at least one clearly-licensed provider option.
- Exact folder naming scheme for organized output (`People/John/…` vs
  `John/…`) — decide during UI design with user feedback.
- Recycle-bin behavior on Linux distros without a standard trash implementation.

---

## 10. Future Scope

Recorded so ideas aren't lost; **none of this constrains V1**.

- **Cloud providers:** Google Drive and similar, with user-granted permission,
  treated as just another folder source.
- Cloud sync between devices.
- Mobile companion apps.
- Object / scene / event recognition; OCR; semantic search.
- Timeline and map views; memory generation.
- Image/photo editing.
- AI chat over the library; generative features.
- Large-library scale-out: approximate nearest-neighbor search (e.g., hnswlib),
  incremental clustering, batched processing (per `prototype/HANDOFF.md` §5).
- Smarter video sampling (scene-change or face-track based, per `prototype/HANDOFF.md` §5).
- **Audio duplicate detection:** matching duplicate/near-duplicate audio files
  (exact hash today only catches byte-identical files; content-based matching
  — e.g. audio fingerprinting — would catch re-encodes, same as image/video
  perceptual hashing does visually).
- Cluster splitting UI; per-face reassignment between people.
- Additional community model providers; GPU acceleration UX.
- Optional headless CLI mode that exposes the V1 engine (spiritual successor to
  `sort_media.py`).
- **Background/always-on duplicate detection.** Today, duplicate review is
  entirely on-demand: a user opens a folder in the Explorer clone and
  explicitly triggers a dedupe scan before anything is found (see the
  `dedupe` tool in `app/src/renderer/src/explorer/tools/dedupe/`, and the
  scan trigger in `backend/src/mediamind/api/routes/scans.py`). The idea for
  a future version is to make this proactive instead:
  - A background watcher observes each registered library for new media
    files (OS file-watch APIs preferred over polling — needs a Windows/Linux
    comparison; polling is the fallback where a native watcher isn't
    available).
  - When a new file appears, run an **incremental** dedupe check — compare
    just the new file's content hash / perceptual hash against the existing
    index — rather than a full-library rescan. This needs a persisted
    per-file hash index outside of a single scan's scope (today,
    `duplicate_members`/hashes only exist for the lifetime of one dedupe
    scan); an efficient near-duplicate lookup structure (e.g. a BK-tree over
    perceptual hashes) would matter once libraries grow past a few thousand
    files, per the existing scale-out note above.
  - A detected duplicate becomes a **staged suggestion** rather than a modal
    interruption — the user reviews it whenever they next open the
    Duplicates tool, not the moment it's found.
  - The Duplicates tool becomes **always populated** from staged suggestions
    across the whole library, instead of being gated on the user first
    opening/selecting a specific folder and clicking "scan." This is a
    meaningful change to the current per-folder-scan model and needs its own
    design pass.
  - The review UI itself (category tabs, bulk actions, per-group
    confirm/dismiss) built for the on-demand flow is meant to be reused as-is
    — the lift here is entirely in the detection trigger and suggestion
    storage, not the review experience.
  - Open questions for whoever picks this up: how suggestions surface to the
    user (a badge count on the tool-rail icon? a system notification?); how
    "incremental" avoids re-hashing an entire library on every file add for
    libraries with many near-duplicate candidates; whether the watcher runs
    as part of the Electron main process or a separate background service.
    None of this is decided — this entry is scoping only.
