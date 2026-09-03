# CLAUDE.md — MediaMind

Guidance for Claude Code (and human contributors) working in this repository.

## What this project is

**MediaMind** is an open-source, AI-powered, **filesystem-first** desktop media
manager. It works directly on real folders the user chooses, helps them find
duplicates and organize media by the people in it, and never hides files inside
a proprietary library.

It is **NOT** a photo gallery and **NOT** a Google Photos replacement. The
filesystem is the source of truth; MediaMind is a safe, transparent assistant
for organizing it.

- License: **Apache-2.0** (application code). Downloadable face-recognition
  models carry their own licenses (e.g., InsightFace `buffalo_l` is
  non-commercial/research-only) — the app must surface a model's license before
  it is downloaded.
- Stack (V1): **Electron + React (TypeScript)** frontend, **Python (FastAPI)**
  backend over localhost HTTP/WebSocket. See `docs/IMPLEMENTATION_PLAN.md`.

## Current state

- **Version 0 (working prototype):** `prototype/sort_media.py` — a validated
  single-file CLI that face-sorts a folder of mixed media.
  `prototype/sort_faces.py` is the earlier images-only version (reference
  only). See `prototype/HANDOFF.md` for the full prototype context.
- **Version 1 (main framework built):** the desktop application's primary UI
  is a full **Windows Explorer clone** (`app/src/renderer/src/explorer/`) —
  navigation pane, tabs, address bar, six view modes including a recursive
  Gallery view, search/filter, drag-and-drop, full context menus, Properties,
  compress/extract, and a Recent Deletions history — scoped to real drives
  and folders and filtered to media. This supersedes the original
  scan/select workflow described in `docs/PRD.md` §5 as V1's UI: the vision
  is now filesystem-first browsing as the primary layer, with duplicate
  detection, face recognition, and organize-by-person layered on top as
  actions inside that shell. The duplicate-detection and face-recognition
  **engine** (backend `core/`, `providers/`) and their original screens
  (`DedupeReview.tsx`, `PeopleScreen.tsx`, etc.) are fully built and tested
  but not yet wired into the Explorer shell — that integration is a
  deliberately deferred, separate effort. `docs/PRD.md` and
  `docs/IMPLEMENTATION_PLAN.md` still describe the target feature set and
  backend architecture accurately; their UI-flow descriptions predate the
  Explorer-clone pivot. See `docs/USER_GUIDE.md` for the current, accurate
  feature list and `.claude/handoffs/` for the session-by-session history of
  how the Explorer clone was built.
- **Version 1.x (current frontend — the WinUI overhaul):** the app's real,
  single intended UI is now the **WinUI Explorer clone** in
  `winui-frontend/Files/` (the "Block 5" overhaul, ADR-0012 — a fork of the
  MIT-licensed Files app), with the Python engine **bundled inside it** and all
  People-flow features surfaced natively (People sidebar, Suggestions,
  per-person Consolidation, consistency check, Watched Folders). This is **not a
  separate app or a side experiment** — it is THE app, replacing the Electron
  frontend above. "Build/release the app" means this WinUI app + bundled engine
  packaged as a (sideload) MSIX — **never** the Electron NSIS build. The Electron
  UI (`app/`) is the previous frontend, kept working but superseded. GitHub
  Releases continue by number (v0.3.x were Electron; v0.4.0+ carry the WinUI
  app). See the `.claude/handoffs/` session history (s73+) and
  `docs/BLOCK5_UI_BLUEPRINT.md`.

## Product identity & UX doctrine (non-negotiable)

MediaMind is a **media-first, feature-rich** file explorer — not a plain file
explorer with media features bolted on. The Files-clone shell is only the base.
Three rules bind every UI change:

1. **Media-first by default.** Folder views show **media** (images/video) by
   default, with a visible toggle to show all files. Never dump PDFs/Word/markdown
   at the user as the default — that is the single thing that makes this MediaMind.
2. **Flagship features are first-class and discoverable.** Scan-for-People, the
   People/Person view, Suggestions, Consolidation, duplicate detection, and
   watch-a-folder are the *highlights* — they belong on visible command bars,
   near the top of the sidebar, and in onboarding. They must **never** be buried
   two or three levels deep (right-click submenus, settings pages) as the only way
   to reach them. Design the information architecture deliberately: sidebar order,
   what a page leads to next, the whole flow.
3. **Cause and effect (visible feedback).** Every backend action MUST produce a
   visible frontend effect — pending state, progress, success, and error — in the
   main UI, not a hidden status flyout or a swallowed log line. A backend action
   with no visible effect is a broken app, regardless of whether the backend
   "worked."

## How to work on this project

- **A specific complaint is an instance of a class, never the whole bug.** When a
  problem is pointed out, infer the intent, then proactively sweep the whole
  affected surface for every sibling instance and fix the class. Do not fix only
  the named item and declare done — that makes the user the QA. The QA is you.
- **Verify end-to-end from the user's perspective**, on realistic data, with the
  result visible on screen — by automation *or* by hand. Never verify on a fixture
  rigged to skip the failing condition, and never report "done/verified" for a
  path exercised only through an API or automation backdoor.
- **Handoffs are proactive and extensive.** Context must survive session
  boundaries (the user works across many short sessions). After meaningful work,
  update `.claude/handoffs/` richly enough that the next session continues without
  re-grilling.
- **Frontend-design skill is mandatory, no exceptions.** Before writing or
  editing any frontend UI code — WinUI XAML, Electron/React, CSS, any visual
  surface — invoke the `frontend-design` skill first, even for a small,
  surgical tweak to an existing view. This is a hard rule (set 2026-09-03
  after a UI change shipped without it); there is no "too small to bother"
  exception. When Hussain sends a concrete visual reference (a screenshot),
  treat it as ground truth to match and use the skill's critique lens to
  avoid generic AI-default patterns in everything the reference doesn't pin
  down.

## Repository map

| Path | Role |
|---|---|
| `backend/` | Python engine package `mediamind` (FastAPI, core pipeline, providers, store). |
| `app/` | Electron + React desktop frontend. |
| `prototype/sort_media.py` | V0 engine. The reference implementation being ported into the backend. Do not break it until its logic is fully ported and tested. |
| `prototype/sort_faces.py` | Original images-only prototype. Reference only. |
| `prototype/HANDOFF.md` | Original prototype handoff (context, decisions, limitations). |
| `docs/PRD.md` | Product requirements for Version 1. |
| `docs/IMPLEMENTATION_PLAN.md` | Architecture, stack, milestones for Version 1. |
| `docs/handoffs/` | Historical session handoffs (sessions 01-08, committed). |
| `.claude/handoffs/` | Current session handoffs (session 09+, gitignored — internal continuity notes, not published). |

**Dev environment:** a Python 3.10+ venv with InsightFace/ONNX/OpenCV
installed (see `backend/pyproject.toml` for exact dependencies). Point
`MAIN_VITE_PYTHON` in `app/.env` (see `app/.env.example`) at that venv's
`python.exe`/`python` for the Electron app to spawn the backend correctly.
Note: NumPy 2.x works fine with insightface 1.0.1 — the `numpy<2` pin
mentioned in the V0 handoff is obsolete for current environments.

## Safety rules (non-negotiable)

These override performance, convenience, and elegance. They exist because users
point MediaMind at irreplaceable personal media.

1. **Never break user media.** No operation may corrupt, truncate, or lose a
   user file — even on crash, power loss, or mid-run failure.
2. **Never delete user files without explicit confirmation.** No automatic
   deletion, ever. Deletion requires a clear, informed user action.
3. **Safety before performance.** A slower safe path beats a faster risky one.
4. **The filesystem is the source of truth.** Databases and caches are indexes
   that can always be rebuilt by rescanning; they never hold data the user
   can't see on disk.
5. **Preserve the V0 safety invariants** in every reimplementation:
   - Moves are **copy-then-delete** (a mid-run failure never loses data).
   - **Everything routes somewhere** — no file is ever silently skipped;
     undecodable or ambiguous files go to a visible holding area.
   - Every file operation is recorded in a **manifest / audit trail**.
   - A **dry-run / preview** mode exists for every destructive-adjacent
     operation and changes nothing.
   - Operations end with a **verifiable count check** (inputs vs. handled).
6. **Review before commit.** Automatic decisions (face matches, dedupe picks)
   go through a user review stage before anything is finalized. Nothing is
   permanently moved without confirmation.
7. **Undo-friendly.** Prefer reversible operations; keep enough information to
   undo the last organization action.

## Git workflow (mandatory, automatic — no confirmation needed)

Hussain does not manage git for this repo; Claude Code does, every session, without being asked.

1. **`main` is never committed to directly.** All work happens on a `development`
   branch (create it if it doesn't exist; branch it from `main` if so).
2. **Commit checkpoints proactively.** Any time a meaningful chunk of
   architectural or feature work is finished — not just when told to commit —
   stage and commit it on `development` with a clear message. Don't let
   finished work sit uncommitted across a session boundary.
3. **Merge `development` → `main` at verified checkpoints**, i.e. once the
   work on `development` builds/typechecks and its tests pass — not mid-feature
   or on unverified code. Use a normal merge (or fast-forward if clean); never
   force-push `main`.
4. Never rewrite `main` history (`reset --hard`, `push --force`, amending
   pushed commits). If `main` and `development` diverge unexpectedly, stop and
   surface it instead of resolving it silently.
5. This overrides the general "commit/push only when asked" default — for
   this repo specifically, git hygiene is Claude's standing responsibility.

## Engineering rules

- **Keep architecture modular.** Small, single-purpose modules with clear
  interfaces. Avoid large files — split before a file grows unwieldy
  (guideline: ~300–400 lines is a smell, not a hard limit).
- **Keep commits focused.** One logical change per commit, with a message that
  explains why.
- **Avoid unnecessary dependencies.** Every new dependency must justify itself;
  prefer the standard library and already-present packages.
- **Write clean documentation.** User docs and developer docs are part of the
  feature, not an afterthought.
- **Keep public APIs stable.** Backend HTTP API, plugin interfaces, and CLI
  flags are contracts. Preserve backward compatibility whenever practical;
  when a break is unavoidable, document the migration.
- **Always explain architectural decisions.** Significant decisions get a short
  rationale in the relevant doc (or the handoff) — what was chosen, what was
  rejected, and why.
- **Prefer readability over cleverness.** Code is read far more than written.
- **Avoid premature optimization.** Optimize when a measurement says so.
- **Cross-platform:** support **Windows first, Linux second, macOS third.**
  Use `pathlib` / path-safe APIs, never hardcode separators, and stay
  unicode-path-safe (the V0 loaders show the pattern).

## Development conventions

- **Python:** 3.10+, PEP 8, type hints on public functions, `pathlib.Path` for
  all paths. Per-file try/except in pipelines — one bad file must never crash a
  run (V0 pattern).
- **TypeScript/React:** strict mode, functional components, no `any` without a
  comment justifying it.
- **Tests:** backend logic gets pytest coverage; face detection stays behind an
  injectable interface so tests never need the 300 MB model (see
  `prototype/HANDOFF.md` §6). Safety invariants (routing, count checks, dry-run,
  copy-then-delete) are the highest-priority test targets.
- **Docs:** product docs in `docs/`, session continuity notes in
  `.claude/handoffs/` (gitignored) or `docs/handoffs/` (historical record),
  user-facing usage in `README.md` files.
- **Dependency note:** insightface 1.0.1 + onnxruntime 1.27 work with
  NumPy 2.x (verified in the dev venv). The V0 handoff's `numpy<2` pin applied
  to older insightface releases only.
