"""Phase 0 baseline harness (Organize-by-Person V3): where does the time go?

Times the real server-side decode pipeline against a folder of media so the
Phase 1 fast-decode + persistent-cache work has a measured before/after to
beat. Import-level, no running app: the `/fs/thumbnail`, `/fs/raw` and
`/fs/list` routes call these exact functions, so these numbers are the server
cost minus negligible FastAPI/HTTP overhead.

What it proves:
  - full-resolution decode dominates every thumbnail (grid tile *and* preview),
    because `_generate_thumbnail_jpeg` decodes the whole original first;
  - the same full decode is what a full-screen open pays (raw bytes stream,
    then the client decodes the original);
  - the in-memory cache is instant on a warm hit but starts empty every launch.

Run:  python backend/scripts/bench_decode.py test/dedupe_review
      python backend/scripts/bench_decode.py <folder> --sample 60
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
from pathlib import Path

from mediamind.core import loaders, thumbnails
from mediamind.core.scanner import MEDIA_KINDS, kind_of

GRID_SIZE = 256      # /fs/thumbnail default (grid tile)
PREVIEW_SIZE = 1024  # largest thumbnail size the route allows (preview pane)
SCREENFUL = 24       # tiles roughly visible on first folder open


def _collect(root: Path, cap: int) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            p = Path(dirpath) / name
            if kind_of(p) in MEDIA_KINDS:
                out.append(p)
                if len(out) >= cap:
                    return out
    return out


def _time(fn) -> tuple[float, object]:
    t0 = time.perf_counter()
    result = fn()
    return (time.perf_counter() - t0) * 1000.0, result  # ms


def _stats(label: str, samples: list[float]) -> str:
    if not samples:
        return f"| {label} | — | — | — | — |"
    return (
        f"| {label} | {statistics.median(samples):.1f} | "
        f"{statistics.mean(samples):.1f} | "
        f"{max(samples):.1f} | {sum(samples):.0f} |"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--sample", type=int, default=60, help="max media files to time")
    args = ap.parse_args()

    root = args.folder.resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a folder: {root}")

    # --- Folder-open cost: the single-level walk `/fs/list` does ---
    list_ms, entries = _time(lambda: list(os.scandir(root)))
    for e in entries:  # `/fs/list` stats every entry
        try:
            e.stat()
        except OSError:
            pass

    files = _collect(root, args.sample)
    if not files:
        raise SystemExit(f"No decodable media under {root}")

    # Warm up the OpenCV/PIL DLLs so the first real sample isn't skewed.
    loaders.load_image(files[0])

    decode_ms: list[float] = []       # full-resolution decode (load_image)
    grid_cold_ms: list[float] = []    # full 256px thumbnail, no cache
    preview_cold_ms: list[float] = [] # full 1024px thumbnail, no cache
    warm_ms: list[float] = []         # second call - in-memory cache hit
    sizes: list[int] = []
    ms_per_mp: list[float] = []       # decode ms per megapixel (scaling)

    for p in files:
        kind = kind_of(p)
        try:
            sizes.append(p.stat().st_size)
        except OSError:
            sizes.append(0)

        dt, frame = _time(lambda: loaders.load_image(p) if kind == "image" else thumbnails._first_frame(p, kind))
        if frame is None:
            continue
        decode_ms.append(dt)
        mp = (frame.shape[0] * frame.shape[1]) / 1_000_000
        if mp > 0.05:
            ms_per_mp.append(dt / mp)

        gt, _ = _time(lambda: thumbnails._generate_thumbnail_jpeg(p, kind, GRID_SIZE))
        grid_cold_ms.append(gt)

        pt, _ = _time(lambda: thumbnails._generate_thumbnail_jpeg(p, kind, PREVIEW_SIZE))
        preview_cold_ms.append(pt)

        thumbnails.media_thumbnail_jpeg(p, kind, GRID_SIZE)  # populate cache
        wt, _ = _time(lambda: thumbnails.media_thumbnail_jpeg(p, kind, GRID_SIZE))
        warm_ms.append(wt)

    n = len(decode_ms)
    med_grid = statistics.median(grid_cold_ms)
    avg_mb = statistics.mean(sizes) / (1024 * 1024) if sizes else 0

    rate = statistics.median(ms_per_mp) if ms_per_mp else 0

    print(f"\n## Phase 0 baseline - {root.name}  (n={n} media files)\n")
    print(f"Single-level list walk (/fs/list): {list_ms:.1f} ms for {len(entries)} entries")
    print(f"Avg original file size: {avg_mb:.2f} MB\n")
    print("| Step (per file, ms) | median | mean | max | total |")
    print("|---|---|---|---|---|")
    print(_stats("Full-res decode (load_image)", decode_ms))
    print(_stats("Grid thumb 256px, cold", grid_cold_ms))
    print(_stats("Preview thumb 1024px, cold", preview_cold_ms))
    print(_stats("Grid thumb 256px, warm (mem cache)", warm_ms))
    print()
    print(f"Decode scaling: ~{rate:.1f} ms per megapixel (median)")
    print(f"Extrapolated folder-open (first {SCREENFUL} tiles, 256px cold, sequential): "
          f"{med_grid * SCREENFUL:.0f} ms")
    print(f"Same {SCREENFUL} tiles if they were real 12MP photos: "
          f"~{rate * 12 * SCREENFUL:.0f} ms; 24MP: ~{rate * 24 * SCREENFUL:.0f} ms")
    print(f"Full-screen open ~= full decode ({statistics.median(decode_ms):.0f} ms here, "
          f"~{rate * 12:.0f} ms for a 12MP photo) + transfer of the whole original")
    print("\nWarm cache is instant but in-memory only - empty on every app launch.\n")


if __name__ == "__main__":
    main()
