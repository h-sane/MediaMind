# MediaMind

**An open-source, AI-powered, filesystem-first media manager.**

MediaMind works directly on real folders you choose — no import step, no
proprietary library, no cloud. It finds duplicate photos and videos, recognizes
the people in your media (with a face-recognition model *you* pick and
download), and helps you organize everything safely: every automatic decision
waits for your review, every file operation is audited, and nothing is ever
deleted without your explicit confirmation.

> **Status: Version 1 in active development.** The validated Version 0
> prototype lives in [`prototype/`](prototype/) and is still usable as a CLI.

## Why MediaMind?

- **Not another photo gallery.** The filesystem is the source of truth.
  MediaMind organizes *your* folders; it doesn't trap media in a library.
- **Local & private.** Everything runs on your machine. No account, no
  telemetry, no network — except the model download you ask for.
- **Safe by design.** Copy-then-delete moves, full audit manifest, dry-run
  previews, review-before-commit, undo. Inherited from a prototype built
  around the rule *"never lose a file."*
- **Open models.** Face recognition providers are downloadable plugins with
  their licenses shown up front. Choose the model that fits your library.

## Version 1 features

1. **Duplicate detection** — exact + near duplicates, resolved in a few clicks.
2. **Face recognition** — zero-training person clustering across photos,
   GIFs, *and videos*, with configurable model providers.
3. **Review before saving** — media with several people gets one final home
   you choose; no duplicate copies.
4. **Person naming** — `Person_001` → `John`, persisted as a known identity.
5. **Known-people matching** — new media lands in *"John (Pending)"* until you
   confirm it.
6. **Review everywhere** — nothing moves permanently without confirmation.

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Product requirements (Version 1) |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Architecture, stack, milestones |
| [`CLAUDE.md`](CLAUDE.md) | Project rules & session workflow |
| [`prototype/HANDOFF.md`](prototype/HANDOFF.md) | Version 0 prototype context |

## Repository layout

```
app/        Electron + React desktop app (frontend)
backend/    Python engine (FastAPI) — scanning, dedupe, faces, safe organizing
prototype/  Version 0 CLI scripts (validated reference implementation)
docs/       Product & engineering documentation
```

## Tech stack

Electron + React + TypeScript (UI) · Python + FastAPI (engine) ·
ONNX Runtime + InsightFace (faces) · scikit-learn DBSCAN (clustering) ·
OpenCV + Pillow/pillow-heif (decoding, incl. HEIC/AVIF) · SQLite (index).

## Development setup

**Prerequisites:** Python 3.11+, Node.js 20+, npm 10+.

```bash
# Backend (Python engine)
python -m venv .venv
# Windows: .venv\Scripts\activate  | Linux/Mac: source .venv/bin/activate
pip install -e "backend[dev]"

# Frontend (Electron + React)
cd app
npm install
```

**Run in dev mode:**

```bash
# Terminal 1 — start the backend
cd backend
python -m mediamind

# Terminal 2 — start the Electron app
cd app
npm run dev
```

**Run backend tests:**

```bash
cd backend
python -m pytest -m "not integration"   # model-free (fast, no GPU needed)
```

**TypeScript check + build:**

```bash
cd app
npm run typecheck   # type checking only
npm run build       # production build (output: app/out/)
```

## Building a release installer

> Requires the backend to be built first with PyInstaller, then the Electron packager.

```bash
# 1. Build the backend bundle (requires pyinstaller)
cd backend
pip install pyinstaller
pyinstaller mediamind.spec
# Output: backend/dist/mediamind/

# 2. Build the app installer
cd app
npm run dist
# Output: app/dist/MediaMind-Setup-<version>.exe  (Windows)
#         app/dist/MediaMind-<version>.dmg         (macOS)
#         app/dist/MediaMind-<version>.AppImage    (Linux)
```

**Model license note:** Face recognition models are downloaded on first use,
with their license shown in-app before download. InsightFace `buffalo_l` is
non-commercial / research-only. OpenCV YuNet+SFace is Apache-2.0 (permissive).

## License

Code: [Apache-2.0](LICENSE). Downloadable face-recognition models carry their
own licenses (shown in-app before download) — e.g., InsightFace's `buffalo_l`
model pack is licensed for non-commercial research use.
