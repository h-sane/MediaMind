"""Media-kind classification for the Explorer shell only.

Extends `core.scanner`'s image/gif/video kinds with "audio" — relevant to
whole-filesystem browsing, search, and preview, but never to the face-
recognition scan/dedupe pipeline (`core/scanner.py`), which has no use for
audio files and must keep classifying them as "other". Keeping this in a
separate module (rather than adding audio to `scanner.MEDIA_KINDS` directly)
means the pipeline's own notion of "media" never changes.
"""

from __future__ import annotations

from pathlib import Path

from mediamind.core.scanner import KIND_OTHER, MEDIA_KINDS, kind_of

KIND_AUDIO = "audio"

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".opus", ".aiff"}

EXPLORER_KINDS = (*MEDIA_KINDS, KIND_AUDIO)


def explorer_kind_of(path: Path) -> str:
    """Same as `scanner.kind_of`, but also recognizes audio files.

    This is the Explorer shell's own broader notion of "media" — used for
    directory listing, recursive search, and the raw-file/metadata routes.
    """
    kind = kind_of(path)
    if kind != KIND_OTHER:
        return kind
    if path.suffix.lower() in AUDIO_EXTS:
        return KIND_AUDIO
    return KIND_OTHER
