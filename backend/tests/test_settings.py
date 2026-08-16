"""`SettingsStore`'s auto-scan mode: 3-tier persistence, back-compat migration
from the old boolean, and the computed `auto_scan_enabled` property.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mediamind.core.settings import SettingsStore


def test_default_mode_is_off(tmp_path: Path) -> None:
    store = SettingsStore(store_path=tmp_path / "settings.json")
    assert store.auto_scan_mode == "off"
    assert store.auto_scan_enabled is False


def test_legacy_boolean_true_migrates_to_libraries(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"recent_files_enabled": True, "auto_scan_enabled": True}), encoding="utf-8")
    store = SettingsStore(store_path=path)
    assert store.auto_scan_mode == "libraries"
    assert store.auto_scan_enabled is True


def test_legacy_boolean_false_migrates_to_off(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"auto_scan_enabled": False}), encoding="utf-8")
    store = SettingsStore(store_path=path)
    assert store.auto_scan_mode == "off"


def test_set_auto_scan_mode_persists_and_rejects_invalid(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(store_path=path)
    assert store.set_auto_scan_mode("system") == "system"
    assert store.auto_scan_enabled is True

    with pytest.raises(ValueError):
        store.set_auto_scan_mode("bogus")

    reloaded = SettingsStore(store_path=path)
    assert reloaded.auto_scan_mode == "system"


def test_set_auto_scan_enabled_shim_maps_to_libraries_tier(tmp_path: Path) -> None:
    store = SettingsStore(store_path=tmp_path / "settings.json")
    store.set_auto_scan_enabled(True)
    assert store.auto_scan_mode == "libraries"
    store.set_auto_scan_enabled(False)
    assert store.auto_scan_mode == "off"
