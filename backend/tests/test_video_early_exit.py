"""ADR-0011 progressive early-exit: a video stops being sampled once its cast
has settled, but keeps going while new distinct people are still appearing, and
non-video media is never early-exited."""

from __future__ import annotations

import numpy as np

from mediamind.core.faces import engine
from mediamind.core.scanner import KIND_GIF, KIND_VIDEO, ScannedFile
from mediamind.providers.fake import FakeColorProvider


def _solid(bgr: tuple[int, int, int]) -> np.ndarray:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[:] = bgr
    return frame


RED, BLUE, GREEN = (0, 0, 255), (255, 0, 0), (0, 255, 0)


def _extract(kind: str, frames: list[np.ndarray], monkeypatch) -> engine.MediaFaces:
    monkeypatch.setattr(engine, "_frames_for", lambda *a, **k: iter(frames))
    sf = ScannedFile(path=__import__("pathlib").Path("x"), kind=kind, size=0, mtime=0.0)
    return engine.extract_file_faces(sf, FakeColorProvider())


def _frames_processed(result: engine.MediaFaces) -> int:
    return max((f.frame_no for f in result.faces), default=-1) + 1


def test_settled_cast_exits_at_min(monkeypatch):
    # Ten identical frames = one person: stop at the floor, not all ten.
    res = _extract(KIND_VIDEO, [_solid(RED)] * 10, monkeypatch)
    assert _frames_processed(res) == engine.VIDEO_MIN_FRAMES


def test_growing_cast_defers_exit(monkeypatch):
    # New person each of the first 3 frames, then repeats: must run past the
    # floor and only exit once nobody new shows up for PATIENCE frames.
    frames = [_solid(RED), _solid(BLUE), _solid(GREEN)] + [_solid(RED)] * 7
    res = _extract(KIND_VIDEO, frames, monkeypatch)
    assert _frames_processed(res) == 3 + engine.VIDEO_EARLY_EXIT_PATIENCE


def test_gif_is_not_early_exited(monkeypatch):
    # Same still-cast frames, but as a GIF: the flat sampling runs all frames.
    res = _extract(KIND_GIF, [_solid(RED)] * 8, monkeypatch)
    assert _frames_processed(res) == 8


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
