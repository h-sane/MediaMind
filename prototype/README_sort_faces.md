# Sort photos by face — quick start

Groups a folder of photos into `Person_01`, `Person_02`, ... folders
automatically. No training, no tagging. CPU-only, works on Windows.

## 1. Install (one time)

Open PowerShell or Command Prompt and run:

```
pip install insightface onnxruntime opencv-python scikit-learn numpy
```

(Python 3.8–3.11 recommended. If `pip` isn't found, install Python from
python.org first and tick "Add to PATH".)

## 2. Run

```
python sort_faces.py "C:\Users\husai\Pictures\my_photos"
```

- First run downloads the face model (~300 MB) once, then it's cached.
- Results land in a new `sorted_by_face` folder **inside** your photos folder.
- Originals are **copied**, not touched. Photos with several people are copied
  into each of their folders. Photos with no face go to `_no_face`.

Pick a different output location:

```
python sort_faces.py "C:\path\to\photos" --out "C:\path\to\sorted"
```

## 3. Tune the grouping

The only knob that matters is `--eps` (how strict the matching is):

```
python sort_faces.py "C:\path\to\photos" --eps 0.55
```

- Same person split across **too many** folders → raise it (try `0.55`, `0.6`).
- **Different** people merged into one folder → lower it (try `0.45`, `0.4`).
- Default is `0.5`, which works for most albums.

Other options: `--move` (move instead of copy), `--min-size 60` (ignore tiny
background faces).

## No-code alternative

If you'd rather not touch the command line at all, InsightFace ships a desktop
GUI that does the same folder clustering with thumbnails you can review:

```
pip install insightface[gui]
```

then launch it per their tutorial: https://www.insightface.ai/guides/insightface-1-0-tutorial
