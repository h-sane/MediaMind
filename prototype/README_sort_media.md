# sort_media.py — flush a folder of mixed media into face-sorted folders

Upgrade of `sort_faces.py`. Handles **all common photo formats (incl. HEIC),
GIFs, and videos**, detects faces inside every one of them, clusters by person
(no training), and **moves** everything out of the source folder into a sorted
output folder. Nothing is left behind.

## Install (in your venv)

```
pip install "numpy<2" insightface onnxruntime opencv-python scikit-learn pillow pillow-heif
```

- `pillow` + `pillow-heif` add HEIC/HEIF/AVIF decoding.
- Videos are read via OpenCV. Common formats (mp4, mov, avi, mkv, webm...) work
  out of the box. If an exotic codec won't open, that file just lands in
  `_unsorted` — it's never lost.

## Run

Default **moves** everything (flushes the folder):

```
python sort_media.py "C:\Users\husai\Pictures\dump"
```

**Preview first (changes nothing):**

```
python sort_media.py "C:\Users\husai\Pictures\dump" --dry-run
```

## Output layout

Inside `sorted_by_face/` (or your `--out`):

| Folder | What goes there |
|---|---|
| `Person_01`, `Person_02`, … | A face cluster. Media with several people is delivered into each person's folder. |
| `_no_face` | Opened fine, but no face detected. |
| `_unsorted` | Only unique/ungroupable faces, **or** a file that couldn't be decoded. |
| `_others` | Non-media files (docs, zips, etc.) — flush mode only. |
| `manifest.csv` | Every source → destination mapping, for auditing before you delete. |

## Options (everything is configurable)

| Flag | Effect |
|---|---|
| `--copy` | Copy instead of move (keeps originals). |
| `--out PATH` | Custom output folder. |
| `--dry-run` | Preview; touch no files. |
| `--media-only` | Leave non-media files in place (skip `_others`). |
| `--no-recursive` | Don't descend into subfolders. |
| `--eps 0.55` | Grouping strictness. Higher merges more; lower splits more. |
| `--min-samples 2` | Min faces to form a person cluster. |
| `--min-size 40` | Ignore faces smaller than N pixels. |
| `--video-frames 15` | Frames sampled per video. |
| `--gif-frames 8` | Frames sampled per GIF. |
| `--skip-video-faces` | Don't analyze videos/GIFs; drop them in `_videos`. |
| `--ctx 0` | Use GPU 0 (default `-1` = CPU). |
| `--det-size 640` | Detector input size. |

## Safe delete workflow

1. `--dry-run` to preview.
2. Real run. Watch for `SAFETY CHECK: PASS` at the end (input count == handled count).
3. Open `manifest.csv` / spot-check a few `Person_*` folders.
4. Only then delete anything. If you ever see `SAFETY CHECK: FAIL`, stop and review.

## Notes on accuracy

Clustering is excellent but not perfect: occasionally one person spans two
`Person_*` folders, or a stranger slips in. That only affects *which* folder a
file lands in — never *whether* it's delivered. Tune with `--eps`.

Videos/GIFs are sorted by the faces found across sampled frames, so a clip with
several people is copied into each of their folders.
