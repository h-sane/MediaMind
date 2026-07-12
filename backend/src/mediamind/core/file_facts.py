"""OS-level file facts (creation date, Windows attributes, owner) for the
Properties panel — kept separate from `thumbnails.py`'s pixel-derived facts
(dimensions/duration) since these come from the filesystem/OS, not from
decoding media content.

Every field is best-effort: a lookup that fails (permissions, unsupported
platform, missing native API) yields None for that field rather than
raising, same "never raise" contract as `thumbnails.py::media_metadata`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

# Windows FILE_ATTRIBUTE_* bit values. `os.stat()` on win32 already exposes
# the raw bitmask via `st_file_attributes` — no ctypes struct needed to read it.
_FILE_ATTRIBUTE_READONLY = 0x1
_FILE_ATTRIBUTE_HIDDEN = 0x2
_FILE_ATTRIBUTE_SYSTEM = 0x4


class StatFacts(NamedTuple):
    created: float | None  # epoch seconds; None if the OS can't report it
    accessed: float | None  # epoch seconds; unreliable on NTFS with atime
    # updates disabled (the Windows default since Vista) — surfaced anyway
    # for Explorer parity, same as Explorer's own Properties dialog does.
    read_only: bool | None
    hidden: bool | None
    system: bool | None


class FileFacts(NamedTuple):
    created: float | None
    accessed: float | None
    read_only: bool | None
    hidden: bool | None
    system: bool | None
    owner: str | None  # "DOMAIN\\user" on Windows, None if lookup fails


def _created_time(path: Path, st) -> float | None:
    if sys.platform == "win32":
        return st.st_ctime  # creation time on Windows, unlike POSIX
    # macOS/BSD expose a true birth time; Linux generally does not.
    return getattr(st, "st_birthtime", None)


def _windows_attributes(st) -> tuple[bool | None, bool | None, bool | None]:
    if sys.platform != "win32":
        return None, None, None
    attrs = getattr(st, "st_file_attributes", None)
    if attrs is None:
        return None, None, None
    return (
        bool(attrs & _FILE_ATTRIBUTE_READONLY),
        bool(attrs & _FILE_ATTRIBUTE_HIDDEN),
        bool(attrs & _FILE_ATTRIBUTE_SYSTEM),
    )


def _windows_owner(path: Path) -> str | None:
    """Best-effort owner lookup via raw ctypes (no pywin32 dependency).

    Explicit argtypes/restype are required here, not optional style — these
    Win32 calls take double-pointer out-params, and a mistyped ctypes call
    against them risks a native access violation (crashes the whole process)
    rather than a catchable Python exception. The outer try/except still
    covers everything else that can go wrong (missing API, bad SID, etc.)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        advapi32.GetNamedSecurityInfoW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD

        advapi32.LookupAccountSidW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(ctypes.c_uint),
        ]
        advapi32.LookupAccountSidW.restype = wintypes.BOOL

        kernel32.LocalFree.argtypes = [ctypes.c_void_p]

        SE_FILE_OBJECT = 1
        OWNER_SECURITY_INFORMATION = 0x00000001

        psid = ctypes.c_void_p()
        psd = ctypes.c_void_p()
        result = advapi32.GetNamedSecurityInfoW(
            str(path),
            SE_FILE_OBJECT,
            OWNER_SECURITY_INFORMATION,
            ctypes.byref(psid),
            None,
            None,
            None,
            ctypes.byref(psd),
        )
        if result != 0 or not psid:
            return None
        try:
            name_buf = ctypes.create_unicode_buffer(256)
            name_len = wintypes.DWORD(256)
            domain_buf = ctypes.create_unicode_buffer(256)
            domain_len = wintypes.DWORD(256)
            sid_use = ctypes.c_uint()
            ok = advapi32.LookupAccountSidW(
                None,
                psid,
                name_buf,
                ctypes.byref(name_len),
                domain_buf,
                ctypes.byref(domain_len),
                ctypes.byref(sid_use),
            )
            if not ok:
                return None
            return f"{domain_buf.value}\\{name_buf.value}" if domain_buf.value else name_buf.value
        finally:
            if psd:
                kernel32.LocalFree(psd)
    except Exception:
        return None


def stat_facts(path: Path, st) -> StatFacts:
    """Creation/access time + Windows attributes derived from a `stat_result`
    the caller already has in hand — no syscalls beyond what `os.stat()`
    already did (`st_atime` is always present; no extra lookup like owner
    needs). Safe to call for every row of a bulk directory listing, unlike
    `file_facts()`'s owner lookup below (two extra Win32 security-API calls
    per file, deliberately kept out of the bulk path)."""
    created = _created_time(path, st)
    read_only, hidden, system = _windows_attributes(st)
    return StatFacts(created=created, accessed=st.st_atime, read_only=read_only, hidden=hidden, system=system)


def file_facts(path: Path) -> FileFacts:
    """OS-level facts for a Properties panel. Never raises — a failed lookup
    yields None for that field rather than propagating."""
    try:
        st = path.stat()
    except OSError:
        return FileFacts(created=None, accessed=None, read_only=None, hidden=None, system=None, owner=None)
    facts = stat_facts(path, st)
    owner = _windows_owner(path)
    return FileFacts(*facts, owner=owner)
