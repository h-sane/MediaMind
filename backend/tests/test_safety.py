"""The non-negotiable safety invariants (CLAUDE.md).

These tests are the project's highest-priority suite: copy-then-delete,
collision-safe naming, manifest completeness, dry-run inertness, count
verification, and per-op fault isolation.
"""

import csv
from pathlib import Path

from mediamind.core.safety import (
    ExecutionReport,
    FileOp,
    execute,
    is_network_location,
    new_manifest_path,
    recycle_bin_supported,
    trash,
    unique_destination,
)


def _mk(path: Path, content: str = "data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_unique_destination_never_overwrites(tmp_path: Path):
    src = _mk(tmp_path / "src" / "a.jpg")
    dest_dir = tmp_path / "out"
    first = unique_destination(dest_dir, src)
    _mk(first)
    second = unique_destination(dest_dir, src)
    _mk(second)
    third = unique_destination(dest_dir, src)
    assert first.name == "a.jpg"
    assert second.name == "a_1.jpg"
    assert third.name == "a_2.jpg"


def test_copy_keeps_original(tmp_path: Path):
    src = _mk(tmp_path / "a.jpg", "photo")
    report = execute([FileOp(src, tmp_path / "out", mode="copy")])
    assert report.ok
    assert src.exists()
    assert (tmp_path / "out" / "a.jpg").read_text() == "photo"


def test_move_is_copy_then_delete(tmp_path: Path):
    src = _mk(tmp_path / "a.jpg", "photo")
    report = execute([FileOp(src, tmp_path / "out", mode="move")])
    assert report.ok
    assert not src.exists()
    assert (tmp_path / "out" / "a.jpg").read_text() == "photo"


def test_move_to_multiple_folders_deletes_source_once_all_copied(tmp_path: Path):
    src = _mk(tmp_path / "a.jpg", "photo")
    ops = [
        FileOp(src, tmp_path / "out1", mode="move"),
        FileOp(src, tmp_path / "out2", mode="move"),
    ]
    report = execute(ops)
    assert report.ok
    assert not src.exists()
    assert (tmp_path / "out1" / "a.jpg").exists()
    assert (tmp_path / "out2" / "a.jpg").exists()


def test_failed_copy_blocks_source_deletion(tmp_path: Path):
    """Copy-then-delete: if any copy of a source fails, the original stays."""
    src = _mk(tmp_path / "a.jpg", "photo")
    bad_dest = tmp_path / "out_ok" / "a.jpg"  # a FILE where a folder is expected
    _mk(bad_dest)
    bad_folder = bad_dest / "sub"  # mkdir under a file -> the copy op fails
    ops = [
        FileOp(src, bad_folder, mode="move"),
        FileOp(src, tmp_path / "out2", mode="move"),
    ]
    report = execute(ops)
    assert not report.ok
    assert src.exists()  # original preserved because one copy failed
    assert (tmp_path / "out2" / "a.jpg").exists()  # good copy still made


def test_dry_run_changes_nothing(tmp_path: Path):
    src = _mk(tmp_path / "a.jpg", "photo")
    manifest = tmp_path / "m.csv"
    report = execute([FileOp(src, tmp_path / "out", mode="move")], manifest, dry_run=True)
    assert report.ok
    assert src.exists()
    assert not (tmp_path / "out").exists()
    rows = list(csv.DictReader(open(manifest, encoding="utf-8")))
    assert rows[0]["action"] == "dry-run-moved"


def test_manifest_records_every_operation(tmp_path: Path):
    a = _mk(tmp_path / "a.jpg")
    b = _mk(tmp_path / "b.jpg")
    manifest = tmp_path / "m.csv"
    execute(
        [FileOp(a, tmp_path / "out", "copy"), FileOp(b, tmp_path / "out", "move")],
        manifest,
    )
    rows = list(csv.DictReader(open(manifest, encoding="utf-8")))
    assert len(rows) == 2
    actions = {Path(r["source"]).name: r["action"] for r in rows}
    assert actions == {"a.jpg": "copied", "b.jpg": "moved"}


def test_one_bad_file_never_aborts_the_batch(tmp_path: Path):
    missing = tmp_path / "ghost.jpg"  # never created
    good = _mk(tmp_path / "good.jpg")
    report = execute(
        [FileOp(missing, tmp_path / "out", "copy"), FileOp(good, tmp_path / "out", "copy")]
    )
    assert not report.ok  # count check catches the failure
    assert report.handled == 1
    assert len(report.errors) == 1
    assert (tmp_path / "out" / "good.jpg").exists()


def test_trash_dry_run_touches_nothing(tmp_path: Path):
    src = _mk(tmp_path / "a.jpg")
    report = trash([src], dry_run=True)
    assert report.ok
    assert src.exists()
    assert report.entries[0].action == "dry-run-trashed"


def test_report_ok_is_the_count_check():
    r = ExecutionReport(planned=2, handled=1)
    assert not r.ok
    r2 = ExecutionReport(planned=2, handled=2)
    assert r2.ok


def test_manifest_path_layout(tmp_path: Path):
    p = new_manifest_path(tmp_path, "organize")
    assert p.parent == tmp_path / "manifests"
    assert p.suffix == ".csv"
    assert "organize" in p.name


def test_unc_path_is_a_network_location():
    """The Cryptomator-vault case from the bug report: a UNC path can never
    use the Windows Recycle Bin, no matter the drive-type lookup result."""
    assert is_network_location(Path(r"\\cryptomator-vault\vault\file.jpg"))


def test_local_path_is_not_a_network_location(tmp_path: Path):
    assert not is_network_location(tmp_path / "file.jpg")


def test_trash_permanent_deletes_the_file(tmp_path: Path):
    """permanent=True is the explicit, separately-confirmed fallback for
    locations where the Recycle Bin isn't available — it should actually
    remove the file and label the action "deleted", not "trashed"."""
    src = _mk(tmp_path / "a.jpg")
    report = trash([src], permanent=True)
    assert report.ok
    assert not src.exists()
    assert report.entries[0].action == "deleted"


def test_recycle_bin_unsupported_on_network_path():
    assert not recycle_bin_supported(Path(r"\\cryptomator-vault\vault\file.jpg"))


def test_recycle_bin_supported_on_ntfs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("mediamind.core.safety.filesystem_name", lambda _p: "NTFS")
    assert recycle_bin_supported(tmp_path)


def test_recycle_bin_supported_on_exfat_removable(tmp_path: Path, monkeypatch):
    """FAT32/exFAT removable drives do support the Recycle Bin — an
    allow-list (not "NTFS-only") must not wrongly flag them."""
    monkeypatch.setattr("mediamind.core.safety.filesystem_name", lambda _p: "exFAT")
    assert recycle_bin_supported(tmp_path)


def test_recycle_bin_unsupported_on_unrecognized_virtual_filesystem(tmp_path: Path, monkeypatch):
    """A WinFsp/Dokan virtual-vault mount reports DRIVE_FIXED (so
    is_network_location misses it) but often a non-standard filesystem name —
    that's the signal recycle_bin_supported must catch."""
    monkeypatch.setattr("mediamind.core.safety.filesystem_name", lambda _p: "FUSE-Cryptomator")
    assert not recycle_bin_supported(tmp_path)


def test_recycle_bin_supported_when_filesystem_unknown(tmp_path: Path, monkeypatch):
    """Unknown filesystem name stays optimistic — the reactive
    _friendly_trash_error fallback is the backstop for anything missed here."""
    monkeypatch.setattr("mediamind.core.safety.filesystem_name", lambda _p: None)
    assert recycle_bin_supported(tmp_path)


def test_trash_error_on_network_path_is_friendly(tmp_path: Path, monkeypatch):
    """A send2trash failure on a network/virtual path should explain *why*
    instead of surfacing the bare COM HRESULT text."""

    def _raise(_path):
        raise OSError(None, None, _path, -2147024809)

    monkeypatch.setattr("send2trash.send2trash", _raise)
    unc_path = Path(r"\\cryptomator-vault\vault\file.jpg")
    report = trash([unc_path])
    assert not report.ok
    assert "network or virtual drive" in report.errors[0].error
