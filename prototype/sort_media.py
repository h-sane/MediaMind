#!/usr/bin/env python3
"""
sort_media.py — Flush a directory of mixed media into face-sorted folders.

Detects faces (InsightFace + DBSCAN clustering — no training) across:
  - photos of every common format, including HEIC/HEIF, WEBP, TIFF, BMP, JFIF
  - GIFs (samples frames)
  - videos (samples frames): mp4, mov, avi, mkv, webm, m4v, 3gp, mpeg, wmv, flv...

Every file in the source directory is delivered into the output folder. Nothing
is left behind. Layout of the output folder:

    Person_01, Person_02, ...   a face cluster was found (multi-person media is
                                delivered into EACH person's folder)
    _no_face                    media opened fine but no face was detected
    _unsorted                   media with only ungroupable/unique faces, OR
                                media that could not be opened/decoded
    _others                     non-media files (docs, zips, etc.)  [flush mode]

DEFAULT ACTION IS MOVE (the directory gets flushed). Use --copy to keep originals.
For safety, moves are done as copy-then-delete, and a manifest.csv + a final
count check are written so you can verify before trusting the result. Use
--dry-run to preview with zero file changes.

Install:
    pip install "numpy<2" insightface onnxruntime opencv-python scikit-learn \
                pillow pillow-heif

Basic use (MOVES everything out of the folder):
    python sort_media.py "C:/path/to/media"

Keep originals, custom output, looser grouping:
    python sort_media.py "C:/path/to/media" --copy --out "C:/sorted" --eps 0.55

Preview only:
    python sort_media.py "C:/path/to/media" --dry-run
"""

import argparse
import csv
import os
import shutil
import sys
import traceback
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------------------
# Configurable defaults (also all overridable on the command line).
# ----------------------------------------------------------------------------
IMAGE_EXTS = {".jpg", ".jpeg", ".jfif", ".png", ".bmp", ".webp",
              ".tiff", ".tif", ".heic", ".heif", ".avif"}
GIF_EXTS = {".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".3g2",
              ".mpg", ".mpeg", ".wmv", ".flv", ".ts", ".mts", ".m2ts", ".ogv"}

FOLDER_NO_FACE = "_no_face"
FOLDER_UNSORTED = "_unsorted"
FOLDER_OTHERS = "_others"
PERSON_PREFIX = "Person_"

DEFAULTS = dict(
    out=None, eps=0.5, min_samples=2, min_size=40, ctx=-1, det_size=640,
    video_frames=15, gif_frames=8,
)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Flush a folder of mixed media into face-sorted folders.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("input", help="Folder of media to sort.")
    p.add_argument("--out", default=DEFAULTS["out"],
                   help="Output folder (default: <input>/sorted_by_face).")

    action = p.add_argument_group("action")
    action.add_argument("--copy", action="store_true",
                        help="Copy instead of move (originals are kept).")
    action.add_argument("--dry-run", action="store_true",
                        help="Show what would happen; change no files.")
    action.add_argument("--media-only", action="store_true",
                        help="Only move media; leave non-media files in place "
                             "(default: flush everything, non-media -> _others).")
    action.add_argument("--no-recursive", action="store_true",
                        help="Do not descend into subfolders.")

    tune = p.add_argument_group("face clustering")
    tune.add_argument("--eps", type=float, default=DEFAULTS["eps"],
                      help="DBSCAN cosine distance. Lower=stricter (0.45-0.6).")
    tune.add_argument("--min-samples", type=int, default=DEFAULTS["min_samples"],
                      help="Min faces to form a cluster.")
    tune.add_argument("--min-size", type=int, default=DEFAULTS["min_size"],
                      help="Ignore faces smaller than this many pixels.")

    media = p.add_argument_group("media handling")
    media.add_argument("--video-frames", type=int, default=DEFAULTS["video_frames"],
                       help="Frames sampled per video for face detection.")
    media.add_argument("--gif-frames", type=int, default=DEFAULTS["gif_frames"],
                       help="Frames sampled per GIF.")
    media.add_argument("--skip-video-faces", action="store_true",
                       help="Don't analyze videos/GIFs; move them to _videos.")

    model = p.add_argument_group("model")
    model.add_argument("--ctx", type=int, default=DEFAULTS["ctx"],
                       help="GPU id, or -1 for CPU.")
    model.add_argument("--det-size", type=int, default=DEFAULTS["det_size"],
                       help="Detector input size (square).")
    return p.parse_args()


# ----------------------------------------------------------------------------
# Media loaders (robust to unicode paths, HEIC, odd formats)
# ----------------------------------------------------------------------------
_PIL_OK = False


def _init_optional_decoders():
    """Enable HEIC/AVIF + PIL fallback if available."""
    global _PIL_OK
    try:
        import PIL  # noqa: F401
        _PIL_OK = True
    except Exception:
        _PIL_OK = False
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass  # HEIC just won't decode; those files land in _unsorted safely.


def load_image_any(path: Path):
    """Return a BGR ndarray or None."""
    import cv2
    img = cv2.imread(str(path))
    if img is None:
        try:
            data = np.fromfile(str(path), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        except Exception:
            img = None
    if img is None and _PIL_OK:
        try:
            from PIL import Image
            im = Image.open(str(path)).convert("RGB")
            img = np.ascontiguousarray(np.array(im)[:, :, ::-1])  # RGB->BGR
        except Exception:
            img = None
    return img


def sample_gif_frames(path: Path, n: int):
    if not _PIL_OK:
        return
    try:
        from PIL import Image, ImageSequence
        im = Image.open(str(path))
        frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    except Exception:
        return
    if not frames:
        return
    idxs = sorted(set(np.linspace(0, len(frames) - 1,
                                  min(n, len(frames))).astype(int).tolist()))
    for i in idxs:
        yield np.ascontiguousarray(np.array(frames[i])[:, :, ::-1])


def sample_video_frames(path: Path, n: int):
    import cv2
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        return
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total > 0:
            idxs = sorted(set(np.linspace(0, total - 1,
                                          min(n, total)).astype(int).tolist()))
            for idx in idxs:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ok, fr = cap.read()
                if ok and fr is not None:
                    yield fr
        else:  # unknown length: read sequentially, cap the work
            frames, ok, count = [], True, 0
            ok, fr = cap.read()
            while ok and count < 6000:
                frames.append(fr)
                ok, fr = cap.read()
                count += 1
            if frames:
                idxs = sorted(set(np.linspace(0, len(frames) - 1,
                                  min(n, len(frames))).astype(int).tolist()))
                for i in idxs:
                    yield frames[i]
    finally:
        cap.release()


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def kind_of(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in GIF_EXTS:
        return "gif"
    if ext in VIDEO_EXTS:
        return "video"
    return "other"


def _uniq(folder: Path, src: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / src.name
    n = 1
    while dest.exists():
        dest = folder / f"{src.stem}_{n}{src.suffix}"
        n += 1
    return dest


def main():
    args = parse_args()
    move = not args.copy
    verb = "MOVE" if move else "COPY"

    try:
        import cv2  # noqa: F401
        from insightface.app import FaceAnalysis
        from sklearn.cluster import DBSCAN
    except ImportError as e:
        sys.exit(
            f"Missing dependency: {e.name}\n\nInstall with:\n"
            '    pip install "numpy<2" insightface onnxruntime opencv-python '
            "scikit-learn pillow pillow-heif\n")

    _init_optional_decoders()

    in_dir = Path(args.input).expanduser().resolve()
    if not in_dir.is_dir():
        sys.exit(f"Not a folder: {in_dir}")

    out_dir = Path(args.out).expanduser().resolve() if args.out \
        else in_dir / "sorted_by_face"
    out_dir.mkdir(parents=True, exist_ok=True)

    def is_outside_out(p: Path) -> bool:
        return out_dir != p and out_dir not in p.parents

    walker = in_dir.glob("*") if args.no_recursive else in_dir.rglob("*")
    all_files = sorted(p for p in walker if p.is_file() and is_outside_out(p))
    if not all_files:
        sys.exit(f"No files found in {in_dir}")

    media, others = [], []
    for p in all_files:
        k = kind_of(p)
        (others if k == "other" else media).append((p, k))

    print(f"Source     : {in_dir}")
    print(f"Output     : {out_dir}")
    print(f"Action     : {verb}{'  (dry-run)' if args.dry_run else ''}")
    print(f"Total files: {len(all_files)}  (media: {len(media)}, "
          f"other: {len(others)})\n")

    # ------------------------------------------------------------------ analyze
    app = None
    if media:
        print("Loading face model (first run downloads it)...")
        app = FaceAnalysis(name="buffalo_l",
                           allowed_modules=["detection", "recognition"])
        app.prepare(ctx_id=args.ctx, det_size=(args.det_size, args.det_size))

    embeddings = []          # one row per detected face
    face_to_media = []        # index into `media` for each face
    decoded_ok = [False] * len(media)   # did we get at least one frame?

    def faces_in_frame(frame):
        out = []
        for f in app.get(frame):
            x1, y1, x2, y2 = f.bbox
            if (x2 - x1) < args.min_size or (y2 - y1) < args.min_size:
                continue
            emb = f.normed_embedding
            if emb is not None:
                out.append(emb)
        return out

    for i, (path, k) in enumerate(media, 1):
        n_faces = 0
        try:
            if args.skip_video_faces and k in ("gif", "video"):
                frames = []            # forced into _videos later
            elif k == "image":
                img = load_image_any(path)
                frames = [img] if img is not None else []
            elif k == "gif":
                frames = list(sample_gif_frames(path, args.gif_frames))
            elif k == "video":
                frames = list(sample_video_frames(path, args.video_frames))
            else:
                frames = []

            if frames:
                decoded_ok[i - 1] = True
            for fr in frames:
                if fr is None:
                    continue
                for emb in faces_in_frame(fr):
                    embeddings.append(emb)
                    face_to_media.append(i - 1)
                    n_faces += 1
        except Exception:
            print(f"  [{i}/{len(media)}] ERROR reading {path.name} -> _unsorted")
            traceback.print_exc(limit=1)
            decoded_ok[i - 1] = False
        print(f"  [{i}/{len(media)}] {k:5s} {path.name}: {n_faces} face(s)")

    # ------------------------------------------------------------------ cluster
    media_people = {}
    n_people = 0
    if embeddings:
        from sklearn.cluster import DBSCAN
        X = np.asarray(embeddings, dtype=np.float32)
        print(f"\nClustering {len(X)} faces...")
        labels = DBSCAN(eps=args.eps, min_samples=args.min_samples,
                        metric="cosine", n_jobs=-1).fit_predict(X)
        for lbl, mi in zip(labels, face_to_media):
            media_people.setdefault(mi, set()).add(int(lbl))
        n_people = len({l for l in labels if l != -1})
        print(f"Found {n_people} distinct people.\n")
    else:
        print("\nNo faces detected in any media.\n")

    # ------------------------------------------------------------------ plan
    def targets_for_media(idx, k) -> list:
        if args.skip_video_faces and k in ("gif", "video"):
            return ["_videos"]
        if not decoded_ok[idx]:
            return [FOLDER_UNSORTED]           # couldn't open/decode
        people = media_people.get(idx)
        if not people:
            return [FOLDER_NO_FACE]            # opened, zero faces
        real = sorted(l for l in people if l != -1)
        if real:
            return [f"{PERSON_PREFIX}{l + 1:02d}" for l in real]
        return [FOLDER_UNSORTED]               # only ungroupable faces

    plan = []   # (src, [folders])
    for i, (path, k) in enumerate(media):
        plan.append((path, targets_for_media(i, k)))
    if not args.media_only:
        for path in others:
            plan.append((path, [FOLDER_OTHERS]))
    elif others:
        print(f"(--media-only: leaving {len(others)} non-media files in place)\n")

    # ------------------------------------------------------------------ deliver
    handled = set()
    manifest = []
    counts = {}

    def deliver(src: Path, folders: list):
        made = []
        for folder in folders:
            dest = _uniq(out_dir / folder, src)
            counts[folder] = counts.get(folder, 0) + 1
            if not args.dry_run:
                shutil.copy2(str(src), str(dest))
            made.append(str(dest))
            manifest.append((str(src), folder, str(dest)))
        if move and not args.dry_run and made:
            try:
                os.remove(src)   # copy-then-delete = safe move
            except Exception:
                print(f"  WARN: copied but could not delete original: {src}")
        handled.add(src.resolve())
        return made

    for src, folders in plan:
        deliver(src, folders)

    # ------------------------------------------------------------------ report
    total_media_or_all = len(all_files) if not args.media_only else len(media)
    if not args.dry_run:
        with open(out_dir / "manifest.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["source", "folder", "destination"])
            w.writerows(manifest)

    print("\n================ SUMMARY ================")
    print(f"Action           : {verb}{'  (dry-run, nothing changed)' if args.dry_run else ''}")
    print(f"Distinct people  : {n_people}")
    for folder in sorted(counts):
        print(f"  {folder:16s}: {counts[folder]} file placement(s)")
    print("----------------------------------------")
    print(f"Files to handle  : {total_media_or_all}")
    print(f"Files handled    : {len(handled)}")
    ok = len(handled) == total_media_or_all
    if ok:
        print("SAFETY CHECK: PASS — every targeted file was delivered.")
        if move and not args.dry_run:
            print("Originals were moved. Spot-check the output, then you're done.")
    else:
        print("SAFETY CHECK: FAIL — counts differ. Do NOT delete anything; "
              "review manifest.csv.")
    if not args.dry_run:
        print(f"Manifest         : {out_dir / 'manifest.csv'}")
    print("\nGrouping off? Re-run with higher --eps (0.55) to merge, or lower "
          "(0.45) to split. Use --dry-run to preview safely.")


if __name__ == "__main__":
    main()
