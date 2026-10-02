# MediaMind

**An open-source, AI-powered, filesystem-first media manager.**

MediaMind works directly on real folders you choose — no import step, no
proprietary library, no cloud. It finds duplicate photos and videos, recognizes
the people in your media (with a face-recognition model *you* pick and
download), and helps you organize everything safely: every automatic decision
waits for your review, every file operation is audited, and nothing is ever
deleted without your explicit confirmation.

> **Status: v0.4 — early release, Windows.** The app is a media-first file
> explorer (a fork of the open-source Files app, WinUI 3) with the Python
> engine bundled inside it: Scan for People, Who's who, Duplicates, a folder
> per person, and watched folders. See the
> [User Guide](docs/USER_GUIDE.md). The validated Version 0 prototype lives
> in [`prototype/`](prototype/) and is still usable as a CLI. Contributions
> welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

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
2. **Face recognition (Beta)** — zero-training person clustering across
   photos, GIFs, *and videos*, with configurable model providers.
3. **Review before saving** — media with several people gets one final home
   you choose; no duplicate copies.
4. **Person naming** — `Person_001` → `John`, persisted as a known identity.
5. **Known-people matching** — new media lands in *"John (Pending)"* until you
   confirm it.
6. **Review everywhere** — nothing moves permanently without confirmation.

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | How to install and use the app |
| [`docs/PRD.md`](docs/PRD.md) | Product requirements (Version 1) |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Architecture, stack, milestones |
| [`CLAUDE.md`](CLAUDE.md) | Project rules & session workflow |
| [`prototype/HANDOFF.md`](prototype/HANDOFF.md) | Version 0 prototype context |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to report bugs, suggest features, or submit code |

## Repository layout

```
winui-frontend/Files/  The app: WinUI 3 frontend (a fork of Files, kept in its
                       own git repository) with the engine bundled inside
backend/               Python engine (FastAPI) — scanning, dedupe, faces,
                       safe organizing
app/                   Previous Electron + React frontend (superseded)
prototype/             Version 0 CLI scripts (validated reference implementation)
docs/                  Product & engineering documentation
```

## Tech stack

WinUI 3 + C#/.NET (UI) · Python + FastAPI (engine) ·
ONNX Runtime + InsightFace (faces) · scikit-learn DBSCAN (clustering) ·
OpenCV + Pillow/pillow-heif (decoding, incl. HEIC/AVIF) · SQLite (index).

## Development setup

**Prerequisites:** Windows 10/11, Python 3.11+, the .NET SDK with the Windows
App SDK build tools.

```bash
# Engine (Python)
python -m venv .venv
.venv\Scripts\activate
pip install -e "backend[dev]"
```

**Build and launch the app** (PowerShell, from `winui-frontend/Files/`):

```powershell
dotnet msbuild src/Files.App/Files.App.csproj -p:Configuration=Debug -p:Platform=x64 -v:m
Start-Process "shell:AppsFolder\FilesDev_ykqwq8d6ps0ag!App"
```

Close the running app before building. The development build starts the
engine straight from `backend/src`, so engine changes take effect on the
next launch.

**Run backend tests:**

```bash
cd backend
python -m pytest -m "not integration and not real_media"   # model-free, fast
```

## Releases

Releases are a sideload package (`MediaMind-<version>-WinUI-x64.zip`) on
GitHub Releases, signed with a test certificate. The install steps are in
the [User Guide](docs/USER_GUIDE.md).

## The previous Electron frontend

`app/` holds the earlier Electron + React app. It still runs from source
(Node.js 20+): `cd app`, `npm install`, `npm run dev`. It gets no new
features.

**Model license note:** Face recognition models are downloaded on first use,
with their license shown in-app before download. InsightFace `buffalo_l` is
non-commercial / research-only. OpenCV YuNet+SFace is Apache-2.0 (permissive).

## License

Code: [Apache-2.0](LICENSE). Downloadable face-recognition models carry their
own licenses (shown in-app before download) — e.g., InsightFace's `buffalo_l`
model pack is licensed for non-commercial research use.
