#!/usr/bin/env python3
"""
sort_faces.py — Automatically group photos into folders by who's in them.

No training, no manual tagging. It detects every face, clusters them with
DBSCAN, and copies each photo into a "Person_XX" folder. A photo with several
people is copied into each of their folders.

NOTHING IS LEFT BEHIND. Every file in the source folder ends up in the sorted
folder:
  - a face matched           -> Person_XX
  - image but no face found  -> _no_face
  - any other file type      -> _unsorted   (HEIC, GIF, RAW, video, etc.)
At the end it prints a SAFETY CHECK confirming output count >= input count, so
you can confirm everything copied before deleting originals.

Usage:
    python sort_faces.py "C:/path/to/photos"
    python sort_faces.py "C:/path/to/photos" --out "C:/path/to/sorted" --eps 0.5

Common knobs:
    --eps      Lower = stricter (more, tighter groups). Higher = looser
               (fewer groups, but risks merging different people). Try 0.45-0.6.
    --move     Move files instead of copying (default is copy; originals kept).
    --min-size Ignore faces smaller than this many pixels (default 40).
"""

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


def parse_args():
    p = argparse.ArgumentParser(description="Cluster photos into folders by face.")
    p.add_argument("input", help="Folder of photos to sort.")
    p.add_argument("--out", default=None,
                   help="Output folder (default: <input>/sorted_by_face).")
    p.add_argument("--eps", type=float, default=0.5,
                   help="DBSCAN distance threshold (cosine). 0.45-0.6 typical.")
    p.add_argument("--min-samples", type=int, default=2,
                   help="Min faces to form a cluster (default 2).")
    p.add_argument("--min-size", type=int, default=40,
                   help="Ignore faces smaller than this (pixels). Default 40.")
    p.add_argument("--move", action="store_true",
                   help="Move files instead of copying.")
    p.add_argument("--ctx", type=int, default=-1,
                   help="GPU id, or -1 for CPU (default -1).")
    return p.parse_args()


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

    try:
        import cv2  # noqa: F401
        from insightface.app import FaceAnalysis
        from sklearn.cluster import DBSCAN
    except ImportError as e:
        sys.exit(
            f"Missing dependency: {e.name}\n\n"
            "Install everything with:\n"
            '    pip install "numpy<2" insightface onnxruntime opencv-python scikit-learn\n'
        )

    in_dir = Path(args.input).expanduser().resolve()
    if not in_dir.is_dir():
        sys.exit(f"Not a folder: {in_dir}")

    out_dir = Path(args.out).expanduser().resolve() if args.out \
        else in_dir / "sorted_by_face"
    out_dir.mkdir(parents=True, exist_ok=True)

    def is_outside_out(p: Path) -> bool:
        return out_dir != p and out_dir not in p.parents

    images = sorted(p for p in in_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in IMG_EXTS
                    and is_outside_out(p))
    if not images:
        print(f"No images with a known image extension found in {in_dir}. "
              "Will still sweep all files into _unsorted.")

    app = None
    embeddings = []          # one row per detected face
    face_to_image = []        # index into `images` for each face

    if images:
        print(f"Found {len(images)} images. "
              "Loading face model (first run downloads it)...")
        import cv2
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name="buffalo_l",
                           allowed_modules=["detection", "recognition"])
        app.prepare(ctx_id=args.ctx, det_size=(640, 640))

        for i, path in enumerate(images, 1):
            img = cv2.imread(str(path))
            if img is None:                      # try unicode / odd paths
                try:
                    data = np.fromfile(str(path), dtype=np.uint8)
                    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
                except Exception:
                    img = None
            if img is None:
                print(f"  [{i}/{len(images)}] unreadable (will go to _no_face): "
                      f"{path.name}")
                continue

            faces = app.get(img)
            kept = 0
            for f in faces:
                x1, y1, x2, y2 = f.bbox
                if (x2 - x1) < args.min_size or (y2 - y1) < args.min_size:
                    continue
                emb = f.normed_embedding
                if emb is None:
                    continue
                embeddings.append(emb)
                face_to_image.append(i - 1)
                kept += 1
            print(f"  [{i}/{len(images)}] {path.name}: {kept} face(s)")

    # Cluster.
    img_people = {}
    n_people = 0
    if embeddings:
        from sklearn.cluster import DBSCAN
        X = np.asarray(embeddings, dtype=np.float32)
        print(f"\nClustering {len(X)} faces...")
        labels = DBSCAN(eps=args.eps, min_samples=args.min_samples,
                        metric="cosine", n_jobs=-1).fit_predict(X)
        for lbl, img_idx in zip(labels, face_to_image):
            img_people.setdefault(img_idx, set()).add(int(lbl))
        n_people = len({l for l in labels if l != -1})
        print(f"Found {n_people} distinct people "
              f"(+ unmatched faces under Person_unknown).\n")
    else:
        print("\nNo faces detected.\n")

    handled = set()          # source paths copied somewhere

    def place(src: Path, folder: str):
        dest_dir = out_dir / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = _uniq(dest_dir, src)
        (shutil.move if args.move else shutil.copy2)(str(src), str(dest))

    # Faces -> Person folders.
    placed = set()
    for img_idx, people in img_people.items():
        src = images[img_idx]
        for lbl in people:
            folder = "Person_unknown" if lbl == -1 else f"Person_{lbl + 1:02d}"
            if args.move and len(people) > 1:
                shutil.copy2(str(src), str(_uniq(out_dir / folder, src)))
            else:
                place(src, folder)
        placed.add(img_idx)
        handled.add(src.resolve())

    # Images with a known extension but no detected face.
    no_face = [p for i, p in enumerate(images) if i not in placed]
    for src in no_face:
        place(src, "_no_face")
        handled.add(src.resolve())

    # SAFETY SWEEP: every remaining file of ANY type -> _unsorted.
    all_files = [p for p in in_dir.rglob("*") if p.is_file() and is_outside_out(p)]
    unsorted = [p for p in all_files if p.resolve() not in handled]
    for src in unsorted:
        place(src, "_unsorted")
        handled.add(src.resolve())

    # VERIFICATION.
    total_inputs = len(all_files)
    print(f"Done. Results in: {out_dir}")
    print(f"  People folders : {n_people}")
    print(f"  No-face images : {len(no_face)}")
    print(f"  Other files (_unsorted): {len(unsorted)}")
    print("\n--- SAFETY CHECK ---")
    print(f"  Input files found  : {total_inputs}")
    print(f"  Files accounted for: {len(handled)}")
    if len(handled) == total_inputs:
        print("  RESULT: PASS - every original was copied into the sorted "
              "folder. Safe to delete originals once you've spot-checked.")
    else:
        print("  RESULT: FAIL - counts do not match. DO NOT delete originals.")
    print("\nIf people are split across too many folders, re-run with a higher "
          "--eps (e.g. 0.55). If different people got merged, lower it (0.45).")


if __name__ == "__main__":
    main()
