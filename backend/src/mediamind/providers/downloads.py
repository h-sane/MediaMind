"""Provider model downloader: resumable, sha256-verified, zip-slip-safe.

Uses stdlib urllib only — no new dependencies.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Callable

from mediamind.core.jobs import JobContext
from mediamind.providers.catalog import CatalogEntry, DownloadFile
from mediamind.providers.manager import ProviderManager

CHUNK = 1 << 18  # 256 KB


class DownloadCancelled(Exception):
    pass


def _default_opener(url: str, headers: dict) -> io.RawIOBase:
    import urllib.request
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=60)  # type: ignore[return-value]


def download_file(
    url: str,
    dest: Path,
    *,
    expected_sha256: str | None,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    opener: Callable[[str, dict], io.RawIOBase] | None = None,
) -> None:
    """Resumable download to dest (atomic via .part temp file).

    - Resumes from an existing .part file using HTTP Range headers.
    - Verifies sha256 after download if expected_sha256 is given.
    - Raises DownloadCancelled on cancel; the .part file is KEPT for resume.
    - Raises ValueError on sha256 mismatch (deletes both .part and dest).
    """
    _opener = opener or _default_opener
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Attempt resume
    start_byte = part.stat().st_size if part.exists() else 0
    headers: dict = {}
    if start_byte > 0:
        headers["Range"] = f"bytes={start_byte}-"

    response = _opener(url, headers)
    content_length_raw = None

    # urllib response object has .headers
    try:
        content_length_raw = response.headers.get("Content-Length")  # type: ignore[union-attr]
    except AttributeError:
        pass

    total_bytes: int = 0
    if content_length_raw:
        try:
            total_bytes = int(content_length_raw) + start_byte
        except ValueError:
            pass

    # 200 means the server ignored Range and sends from byte 0 — restart
    status_code = getattr(response, "status", getattr(response, "code", 0))
    if status_code == 200 and start_byte > 0:
        start_byte = 0
        part.unlink(missing_ok=True)

    mode = "ab" if start_byte > 0 else "wb"
    done = start_byte
    hasher = hashlib.sha256() if expected_sha256 else None

    with open(part, mode) as fh:
        # Hash what was already downloaded if resuming
        if hasher and start_byte > 0:
            with open(part, "rb") as existing:
                while chunk := existing.read(CHUNK):
                    hasher.update(chunk)
        while True:
            if should_cancel and should_cancel():
                raise DownloadCancelled()
            chunk = response.read(CHUNK)  # type: ignore[union-attr]
            if not chunk:
                break
            fh.write(chunk)
            if hasher:
                hasher.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total_bytes)

    if expected_sha256 and hasher:
        actual = hasher.hexdigest()
        if actual != expected_sha256:
            part.unlink(missing_ok=True)
            dest.unlink(missing_ok=True)
            raise ValueError(
                f"SHA-256 mismatch for {url}: expected {expected_sha256}, got {actual}"
            )

    part.rename(dest)


def _flatten_zip(archive: Path, dest_dir: Path) -> None:
    """Extract a zip, stripping a single top-level directory if present.

    buffalo_l.zip may contain files directly or under a 'buffalo_l/' prefix.
    Either layout is handled: flatten if there's a single top-level dir,
    else extract flat.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "r") as zf:
        names = zf.namelist()
        # Detect single top-level dir
        top_dirs = {n.split("/")[0] for n in names if "/" in n}
        has_single_top = (
            len(top_dirs) == 1
            and all(n.startswith(next(iter(top_dirs)) + "/") for n in names if "/" in n)
        )
        prefix = (next(iter(top_dirs)) + "/") if has_single_top else ""

        for member in zf.infolist():
            name = member.filename
            if has_single_top and name.startswith(prefix):
                name = name[len(prefix):]
            if not name or name.endswith("/"):
                continue
            member_dest = (dest_dir / name).resolve()
            if not str(member_dest).startswith(str(dest_dir.resolve())):
                raise ValueError(f"Zip-slip detected: {member.filename}")
            member_dest.parent.mkdir(parents=True, exist_ok=True)
            member_dest.write_bytes(zf.read(member.filename))


def make_download_runner(
    entry: CatalogEntry,
    manager: ProviderManager,
    opener: Callable[[str, dict], io.RawIOBase] | None = None,
) -> Callable[[JobContext], dict]:
    """Build a JobManager runner that downloads, verifies, and extracts a provider."""

    def runner(ctx: JobContext) -> dict:
        models_root = manager._root
        extract_dir = models_root / entry.extract_subdir
        extract_dir.mkdir(parents=True, exist_ok=True)

        for i, dl_file in enumerate(entry.downloads):
            # "direct" downloads go straight into extract_dir; zip archives land
            # in models_root then are extracted into extract_dir.
            if entry.archive == "direct":
                dest_path = extract_dir / dl_file.filename
            else:
                dest_path = models_root / dl_file.filename

            file_label = f"file {i + 1}/{len(entry.downloads)}: {dl_file.filename}"

            def _progress(done: int, total: int, _label: str = file_label) -> None:
                ctx.report_progress(done, total, f"downloading {_label}")

            try:
                download_file(
                    dl_file.url,
                    dest_path,
                    expected_sha256=dl_file.sha256,
                    progress=_progress,
                    should_cancel=ctx.cancelled,
                    opener=opener,
                )
            except DownloadCancelled:
                return {}  # .part kept for resume

            ctx.report_progress(0, 0, "verifying")
            # sha256 already verified inside download_file if expected_sha256 set

            if entry.archive == "zip":
                ctx.report_progress(0, 0, "extracting")
                _flatten_zip(dest_path, extract_dir)
                dest_path.unlink(missing_ok=True)  # clean up archive after extraction

        manager.mark_installed(entry.id)
        return {"provider_id": entry.id, "installed": True}

    return runner
