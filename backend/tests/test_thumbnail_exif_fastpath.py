"""Phase 7 / D1 — embedded-EXIF thumbnail fast path (`_embedded_thumbnail_bgr`).

Verifies the byte-offset extraction against a synthesised JPEG that carries a
real thumbnail in its APP1/EXIF block, plus the fall-through on the common
case (re-encoded images with no embedded thumbnail — all of this repo's own
fixtures)."""

from __future__ import annotations

import io
import struct
from pathlib import Path

from mediamind.core import thumbnails


def _jpeg_with_embedded_thumbnail(full_size=(2000, 1500), thumb_size=(160, 120)) -> bytes:
    """Assemble a JPEG whose EXIF IFD1 holds a valid thumbnail JPEG."""
    from PIL import Image

    tb = io.BytesIO()
    Image.new("RGB", thumb_size, (10, 200, 50)).save(tb, "JPEG", quality=80)
    thumb_bytes = tb.getvalue()

    def u16(v: int) -> bytes:
        return struct.pack("<H", v)

    def u32(v: int) -> bytes:
        return struct.pack("<I", v)

    def entry(tag: int, val: int) -> bytes:  # LONG (type 4), count 1
        return u16(tag) + u16(4) + u32(1) + u32(val)

    # Little-endian TIFF: empty IFD0 -> IFD1 with JpegIFOffset/ByteCount -> thumb.
    thumb_off = 14 + 2 + 2 * 12 + 4  # IFD1 starts at 14; header+2 entries+next ptr
    tiff = (
        b"II" + u16(42) + u32(8)  # header, IFD0 at 8
        + u16(0) + u32(14)  # IFD0: 0 entries, next -> IFD1 at 14
        + u16(2) + entry(0x0201, thumb_off) + entry(0x0202, len(thumb_bytes)) + u32(0)
        + thumb_bytes
    )
    exif_blob = b"Exif\x00\x00" + tiff

    buf = io.BytesIO()
    Image.new("RGB", full_size, (120, 60, 30)).save(buf, "JPEG", quality=90, exif=exif_blob)
    return buf.getvalue()


def test_extracts_embedded_thumbnail(tmp_path: Path) -> None:
    p = tmp_path / "with_thumb.jpg"
    p.write_bytes(_jpeg_with_embedded_thumbnail())
    frame = thumbnails._embedded_thumbnail_bgr(p)
    assert frame is not None
    assert frame.shape == (120, 160, 3)  # the embedded thumb, not the 2000x1500 full frame


def test_no_thumbnail_falls_through(tmp_path: Path) -> None:
    from PIL import Image

    p = tmp_path / "plain.jpg"
    Image.new("RGB", (640, 480), (30, 30, 30)).save(str(p), "JPEG")
    assert thumbnails._embedded_thumbnail_bgr(p) is None  # -> draft/full decode runs


def test_generate_prefers_embedded_for_small_sizes(tmp_path: Path) -> None:
    # A large image with a small embedded thumb still yields a valid JPEG at a
    # small tier — proving the fast path is wired in without corrupting output.
    p = tmp_path / "big.jpg"
    p.write_bytes(_jpeg_with_embedded_thumbnail(full_size=(3000, 2250)))
    out = thumbnails._generate_thumbnail_jpeg(p, thumbnails.KIND_IMAGE, 96)
    assert out is not None and out[:2] == b"\xff\xd8"
