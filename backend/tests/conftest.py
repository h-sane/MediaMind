"""Shared fixtures: synthetic media, no ML models required."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


def make_image(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (64, 64)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def make_gif(path: Path, color: tuple[int, int, int], frames: int = 4) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    imgs = [Image.new("RGB", (64, 64), color) for _ in range(frames)]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=100, loop=0)
    return path


RED = (255, 0, 0)
BLUE = (0, 0, 255)
BLACK = (0, 0, 0)


@pytest.fixture
def media_library(tmp_path: Path) -> Path:
    """A folder with: 2 red images, 2 blue images, 1 red GIF, 1 black
    (face-free) image, 1 corrupt jpg, 1 non-media file, 1 nested red image.

    With FakeColorProvider: red media = person A, blue = person B.
    """
    make_image(tmp_path / "red1.jpg", RED)
    make_image(tmp_path / "red2.png", RED)
    make_image(tmp_path / "nested" / "red3.jpg", RED)
    make_image(tmp_path / "blue1.jpg", BLUE)
    make_image(tmp_path / "blue2.jpg", BLUE)
    make_gif(tmp_path / "red.gif", RED)
    make_image(tmp_path / "black.jpg", BLACK)
    (tmp_path / "corrupt.jpg").write_bytes(b"this is not a jpeg")
    (tmp_path / "notes.txt").write_text("not media")
    return tmp_path
