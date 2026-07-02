# HANDOFF — Face/Media Sorter (open-source project kickoff)

**Date:** 2026-07-02
**Purpose:** Transfer full context so a fresh agent (in Claude Code) can turn the
working prototype into a full-fledged open-source project.
**Author of prototype work:** Hussain + Claude (Cowork session)

---

## 1. What this is

A local, CPU-only command-line tool that scans a directory of mixed media,
detects faces, clusters them **without any training or manual tagging**, and
sorts every file into per-person folders. Built to replace a painful digiKam
workflow (manual face training + no auto-foldering).

Core engine: **InsightFace** (`buffalo_l` model pack) for detection + 512-d face
embeddings, and **DBSCAN** (cosine distance) for unsupervised clustering. Chosen
over dlib/`face_recognition` because it pip-installs cleanly on Windows with no
compiler, runs CPU-only, and — importantly for this user — is strong on **Asian
faces** (trained on Glint360K).

Status: **working prototype, single file.** The user has run it successfully and
reports face grouping "worked too well." Ready to be productized.

---

## 2. Current state of the code

Two scripts exist (both standalone, no package structure yet):

### `sort_faces.py` — original (images only)
The first working version. Images only (`.jpg .jpeg .png .bmp .webp .tiff`),
copy-by-default, folders: `Person_XX`, `Person_unknown`, `_no_face`. This is what
the user actually ran and validated. Kept for reference.

### `sort_media.py` — current, expanded (THIS IS THE ONE TO BUILD ON)
Superset rewrite. Key capabilities:

- **Formats:** all common images **including HEIC/HEIF/AVIF** (via `pillow` +
  `pillow-heif`), **GIFs** (PIL frame sampling), and **videos** (OpenCV
  `VideoCapture` frame sampling): mp4, mov, avi, mkv, webm, m4v, 3gp, mpeg, wmv,
  flv, ts, mts, m2ts, ogv.
- **Faces in video/GIF:** samples N frames, runs detection on each, and clusters
  those embeddings together with the photo embeddings in one global DBSCAN pass,
  so a clip is delivered into every person's folder it contains.
- **Default action = MOVE** (flushes the source directory). `--copy` keeps
  originals. Moves are implemented as **copy-then-delete** so a mid-run failure
  never loses data.
- **Nothing left behind.** Output layout:
  - `Person_01/02/...` — clustered people (multi-person media copied to each)
  - `_no_face` — decoded OK, zero faces
  - `_unsorted` — only ungroupable/unique faces, OR file that couldn't be decoded
  - `_others` — non-media files (flush mode; skipped under `--media-only`)
  - `_videos` — only when `--skip-video-faces` is used
- **Safety:** writes `manifest.csv` (source → folder → destination), prints a
  final `SAFETY CHECK: PASS/FAIL` comparing input count vs files handled, and
  supports `--dry-run` (touch nothing).
- **Robustness:** per-file try/except (one bad file can't crash the run),
  unicode-path-safe loading (cv2 → `np.fromfile`+imdecode → PIL fallback).

### Pipeline (sort_media.py)
1. Walk input dir (`rglob`, or `glob` with `--no-recursive`), excluding the
   output dir. Classify each file: image / gif / video / other by extension.
2. Load InsightFace `FaceAnalysis(name="buffalo_l", modules=[detection,
   recognition])`, `prepare(ctx_id, det_size)`.
3. For each media file, extract frames (1 for image, N for gif/video), run
   `app.get()`, filter faces below `--min-size`, collect `normed_embedding`s.
   Track `face_to_media` index and a `decoded_ok` flag per file.
4. One `DBSCAN(eps, min_samples, metric="cosine")` over all embeddings →
   `media_people[file_idx] = set(labels)`.
5. `targets_for_media()` routing:
   - not decoded → `_unsorted`
   - decoded, no faces → `_no_face`
   - has real (non-`-1`) labels → each `Person_XX`
   - only `-1` (noise) → `_unsorted`
6. `deliver()` copies to each target folder (collision-safe `_uniq` naming),
   then deletes original if moving. Records manifest + counts.
7. Report + safety check.

---

## 3. Configuration surface (already implemented)

`input` (positional), `--out`, `--copy`, `--dry-run`, `--media-only`,
`--no-recursive`, `--eps` (default 0.5), `--min-samples` (2), `--min-size` (40),
`--video-frames` (15), `--gif-frames` (8), `--skip-video-faces`, `--ctx` (-1 =
CPU), `--det-size` (640). Tunable module constants at top of file: `IMAGE_EXTS`,
`GIF_EXTS`, `VIDEO_EXTS`, folder names, `DEFAULTS`.

**Tuning guidance:** same person split across folders → raise `--eps` (0.55);
different people merged → lower it (0.45). Default 0.5 works for most albums.

---

## 4. Dependencies

```
pip install "numpy<2" insightface onnxruntime opencv-python scikit-learn pillow pillow-heif
```

- `numpy<2` pin is REQUIRED — InsightFace/onnxruntime still expect NumPy 1.x;
  NumPy 2 is the main source of install conflicts. Install it first.
- `pillow-heif` → HEIC/AVIF. `opencv-python` bundles ffmpeg for common video
  codecs; exotic codecs may fail to open (those files fall to `_unsorted`, never
  lost). Recommended dev setup: a clean venv.
- First run downloads the `buffalo_l` model (~300 MB) to `~/.insightface`, cached
  thereafter.

---

## 5. Known limitations / gaps (candidates for the roadmap)

- **No tests.** Nothing is automated. Highest priority for open-sourcing.
- **Verified only by the author's manual runs.** Face detection was NOT run in
  the build sandbox (InsightFace not installed there); only `py_compile` + logic
  checks passed. Needs real integration tests on sample media.
- **No progress bar / resumability.** Large libraries re-process from scratch;
  no embedding cache. A cache of embeddings keyed by file hash would let re-runs
  (e.g. to re-tune `--eps`) skip re-detection.
- **Clustering is global and in-memory.** Fine for thousands of faces; tens of
  thousands may want batching / approximate NN (e.g. hnswlib) or incremental
  clustering.
- **No person naming / labeling.** Folders are `Person_01`... A follow-up "label
  a folder, then match new photos to known people" mode would be valuable.
- **Video sampling is uniform.** Could use scene-change or face-track sampling
  for better recall on long clips.
- **`--skip-video-faces` routes to `_videos`** but that folder isn't documented
  in the output table — minor doc cleanup.
- **No config file.** Everything is CLI flags; a `--config yaml` or pyproject
  `[tool.facesort]` section could help power users.

---

## 6. Roadmap to a real open-source project

Suggested phased plan for the next agent:

### Phase 1 — packaging & structure
- Convert to a package, e.g. `facesort/` with `__init__.py`, `cli.py`,
  `pipeline.py`, `loaders.py` (image/gif/video), `clustering.py`, `delivery.py`.
- `pyproject.toml` (PEP 621), console entry point `facesort = "facesort.cli:main"`.
- Pin deps with extras: `[gpu]` (onnxruntime-gpu), `[heic]` (pillow-heif).
- Pick a name (e.g. `facesort`, `facesift`, `phototriage`) and check PyPI
  availability.

### Phase 2 — tests & CI
- `pytest` with a tiny fixture set: a few synthetic faces (can generate with PIL),
  a short generated video, a gif, a HEIC, a non-media file.
- Unit-test routing (`targets_for_media`), `_uniq` collision handling, safety
  count, dry-run (asserts no filesystem changes), move = copy-then-delete.
- GitHub Actions matrix (Linux/Windows/macOS, py3.9–3.12). Mock or cache the
  model download; consider a `--model` flag to point at a local model dir for CI.

### Phase 3 — features
- Embedding cache (skip re-detection on re-run) — biggest UX win for `--eps`
  tuning.
- `--dry-run` HTML/preview report with thumbnails per cluster.
- Known-people mode: save cluster centroids, label them, match new imports.
- Progress bars (`tqdm`), structured logging (`--verbose`/`--quiet`).
- Optional GPU path documented.

### Phase 4 — docs & release
- README with GIF demo, install, quickstart, tuning, safety workflow.
- `LICENSE` (MIT or Apache-2.0 recommended). NOTE: verify InsightFace model
  licensing — the InsightFace pretrained models (incl. `buffalo_l`) carry
  **non-commercial / research** terms; document this clearly and consider an
  alternative model or an explicit "personal use" note before redistributing.
- `CONTRIBUTING.md`, issue templates, `CHANGELOG.md`.
- Publish to PyPI; tag a v0.1.0.

### First concrete tasks for the new session
1. Scaffold the package + `pyproject.toml`, move `sort_media.py` logic into
   modules, keep a thin `cli.py`.
2. Add a `--selftest` that generates synthetic media and verifies decode +
   detect + cluster + deliver end-to-end (the user already asked about this).
3. Write the first pytest suite around routing/safety (factor detection behind
   an injectable interface so tests don't need the model).
4. Resolve the model-license question before any PyPI release.

---

## 7. File index

| File | Role |
|---|---|
| `sort_media.py` | **Current** engine. Build the package from this. Images (incl. HEIC/AVIF) + GIF + video face sorting, move-by-default, flush, manifest, dry-run, safety check. |
| `sort_faces.py` | Original images-only prototype (validated by user). Reference only. |
| `README_sort_media.md` | User-facing usage/README for the current script. |
| `README_sort_faces.md` | README for the original script. |
| `manifest.csv` | Generated at runtime in the output dir — source→destination audit trail. |

---

## 8. Design decisions worth preserving

- **InsightFace over face_recognition/dlib:** clean Windows install, CPU-only,
  strong on Asian faces (Glint360K). Deliberate choice for the user's dataset.
- **DBSCAN, not k-means:** number of people is unknown; DBSCAN discovers it and
  marks singletons/outliers as noise (`-1`) instead of forcing them into a group.
- **Global clustering across photos + video frames:** unifies identities so a
  person in a video and in a photo share one `Person_XX` folder.
- **Copy-then-delete moves + manifest + PASS/FAIL check:** the user intends to
  delete originals, so data-loss safety is a first-class requirement — keep it.
- **Everything routes somewhere:** no file is ever skipped; undecodable/ambiguous
  files go to `_unsorted`, non-media to `_others`. This invariant is what makes
  "flush the folder then delete originals" safe. Preserve it in the refactor.
