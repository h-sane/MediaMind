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
