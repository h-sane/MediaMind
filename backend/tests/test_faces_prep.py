"""Tests for the faces pre-scan folder-structure check (core/faces/folder_prep.py)."""

from __future__ import annotations

from pathlib import Path

from mediamind.core.faces.folder_prep import build_unsorted_moves, scan_folder_prep


def test_loose_files_only_no_subfolders(tmp_path: Path):
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        (tmp_path / name).write_bytes(b"")

    result = scan_folder_prep(tmp_path)
    assert result.has_subfolders is False
    assert result.recommend_unsorted is False
    assert result.top_level_loose_count == 3
    assert result.named_subfolder_count == 0


def test_named_subfolder_plus_loose_files_recommends_unsorted(tmp_path: Path):
    (tmp_path / "Laura").mkdir()
    (tmp_path / "Laura" / "img.jpg").write_bytes(b"")
    (tmp_path / "loose1.jpg").write_bytes(b"")
    (tmp_path / "loose2.jpg").write_bytes(b"")

    result = scan_folder_prep(tmp_path)
    assert result.has_subfolders is True
    assert result.recommend_unsorted is True
    assert result.named_subfolder_count == 1
    assert result.top_level_loose_count == 2


def test_named_subfolder_no_loose_files_no_recommendation(tmp_path: Path):
    (tmp_path / "Laura").mkdir()
    (tmp_path / "Laura" / "img.jpg").write_bytes(b"")

    result = scan_folder_prep(tmp_path)
    assert result.has_subfolders is True
    assert result.recommend_unsorted is False
    assert result.top_level_loose_count == 0


def test_build_unsorted_moves_only_top_level_files(tmp_path: Path):
    (tmp_path / "Laura").mkdir()
    (tmp_path / "Laura" / "nested.jpg").write_bytes(b"")
    (tmp_path / "loose1.jpg").write_bytes(b"")
    (tmp_path / "loose2.jpg").write_bytes(b"")
    (tmp_path / "notes.txt").write_bytes(b"")  # not a media kind — excluded

    moves = build_unsorted_moves(tmp_path)
    assert {p.name for p in moves} == {"loose1.jpg", "loose2.jpg"}
