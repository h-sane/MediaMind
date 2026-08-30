"""Face extraction over mixed media (ported from V0's analyze loop).

For each file: decode frames (1 for an image, N sampled for GIF/video), run
the provider on every frame, keep faces above the minimum size. Per-file
fault isolation is preserved — one bad file can never crash a scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

from mediamind.core import loaders
from mediamind.core.scanner import KIND_GIF, KIND_IMAGE, KIND_VIDEO, ScannedFile
from mediamind.providers.base import FaceProvider

# Hard frame-budget cap per video (ADR-0011: "never more than ~10"). The
# progressive early-exit below samples toward this cap but stops as soon as the
# cast has settled, so the common single-subject clip costs ~2-3 frames, not 10
# — every skipped frame is one fewer seek+read on a streamed cloud file.
DEFAULT_VIDEO_FRAMES = 10
DEFAULT_GIF_FRAMES = 8
DEFAULT_MIN_FACE_SIZE = 40

# Progressive early-exit tuning (ADR-0011). A video's frames are sampled spread
# across its length; after each we track the set of *distinct* people seen and
# stop once that set stops growing. The stop signal is "found nobody new for a
# few frames", NOT "found a named person" — stopping on first hit would miss
# co-appearing people. Constants are the recall/speed calibration knob:
#   VIDEO_DISTINCT_SIM  a kept face is a *new* person if its cosine similarity
#                       to every distinct face seen so far is below this.
#   VIDEO_EARLY_EXIT_PATIENCE  stop after this many consecutive frames add
#                       nobody new (a frame with zero faces counts as "nobody").
#   VIDEO_MIN_FRAMES    never exit before sampling this many frames, so a person
#                       who only appears a couple of frames in still gets a look.
VIDEO_DISTINCT_SIM = 0.5
VIDEO_EARLY_EXIT_PATIENCE = 2
VIDEO_MIN_FRAMES = 3


@dataclass(frozen=True)
class FaceRecord:
    """One face detected in one frame of one media file."""

    frame_no: int                                    # index in the sampled frame sequence
    bbox: tuple[float, float, float, float]          # x1, y1, x2, y2 (pixels)
    embedding: np.ndarray                            # float32, L2-normalized

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]


@dataclass
class MediaFaces:
    """Face-extraction result for one media file."""

    file: ScannedFile
    decoded_ok: bool
    faces: list[FaceRecord] = field(default_factory=list)

    @property
    def embeddings(self) -> list[np.ndarray]:
        """Back-compat: clustering.py only needs the embedding vectors."""
        return [f.embedding for f in self.faces]


def _frames_for(file: ScannedFile, video_frames: int, gif_frames: int) -> Iterator[np.ndarray]:
    if file.kind == KIND_IMAGE:
        img = loaders.load_image(file.path)
        if img is not None:
            yield img
    elif file.kind == KIND_GIF:
        yield from loaders.sample_gif_frames(file.path, gif_frames)
    elif file.kind == KIND_VIDEO:
        yield from loaders.sample_video_frames(file.path, video_frames)


def extract_file_faces(
    file: ScannedFile,
    provider: FaceProvider,
    *,
    video_frames: int = DEFAULT_VIDEO_FRAMES,
    gif_frames: int = DEFAULT_GIF_FRAMES,
    min_face_size: int = DEFAULT_MIN_FACE_SIZE,
) -> MediaFaces:
    """Extract faces from a single media file.

    Per-file fault isolation: on any exception, decoded_ok=False and faces=[].
    """
    result = MediaFaces(file=file, decoded_ok=False)
    is_video = file.kind == KIND_VIDEO
    distinct: list[np.ndarray] = []   # one embedding per distinct person seen so far
    stale = 0                         # consecutive frames that added nobody new
    frames_seen = 0
    try:
        for frame_no, frame in enumerate(_frames_for(file, video_frames, gif_frames)):
            if frame is None:
                continue
            result.decoded_ok = True
            added_new = False
            for face in provider.get_faces(frame):
                w = face.bbox[2] - face.bbox[0]
                h = face.bbox[3] - face.bbox[1]
                if w < min_face_size or h < min_face_size:
                    continue
                embedding = np.asarray(face.embedding, dtype=np.float32)
                result.faces.append(FaceRecord(frame_no=frame_no, bbox=face.bbox, embedding=embedding))
                if is_video and not any(float(np.dot(embedding, d)) >= VIDEO_DISTINCT_SIM for d in distinct):
                    distinct.append(embedding)
                    added_new = True

            if is_video:
                frames_seen += 1
                stale = 0 if added_new else stale + 1
                if frames_seen >= VIDEO_MIN_FRAMES and stale >= VIDEO_EARLY_EXIT_PATIENCE:
                    break  # cast has settled — skip the remaining sampled frames
    except Exception:
        result.decoded_ok = False
        result.faces.clear()
    return result


def extract_faces(
    files: list[ScannedFile],
    provider: FaceProvider,
    *,
    video_frames: int = DEFAULT_VIDEO_FRAMES,
    gif_frames: int = DEFAULT_GIF_FRAMES,
    min_face_size: int = DEFAULT_MIN_FACE_SIZE,
    progress: Callable[[int, int, ScannedFile], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[MediaFaces]:
    """Extract faces from a list of media files."""
    provider.prepare()
    results: list[MediaFaces] = []
    total = len(files)

    for i, file in enumerate(files, 1):
        result = extract_file_faces(
            file, provider,
            video_frames=video_frames,
            gif_frames=gif_frames,
            min_face_size=min_face_size,
        )
        results.append(result)
        if progress is not None:
            progress(i, total, file)
        if should_cancel is not None and should_cancel():
            break
    return results


def load_frame(
    path: Path,
    kind: str,
    frame_no: int,
    *,
    video_frames: int = DEFAULT_VIDEO_FRAMES,
    gif_frames: int = DEFAULT_GIF_FRAMES,
) -> np.ndarray | None:
    """Re-decode exactly the frame `frame_no` refers to.

    For images, frame_no 0 is the only valid index. For GIF/video, frame_no
    is the index within the sampled sequence (same defaults as extraction).
    Returns None if the frame index is out of range or decoding fails.
    """
    from mediamind.core.scanner import KIND_GIF, KIND_IMAGE, KIND_VIDEO

    class _Stub:
        def __init__(self, p: Path, k: str) -> None:
            self.path = p
            self.kind = k

    stub = _Stub(path, kind)
    try:
        for i, frame in enumerate(_frames_for(stub, video_frames, gif_frames)):  # type: ignore[arg-type]
            if i == frame_no:
                return frame
    except Exception:
        pass
    return None
