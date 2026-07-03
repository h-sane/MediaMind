"""Provider manager: installed-state tracking and provider factory.

Lives on app.state.providers. Tests inject a ProviderManager with a custom
catalog and a tmp models_root — no model download needed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from mediamind.providers.base import FaceProvider
from mediamind.providers.catalog import CATALOG, CatalogEntry


class ProviderManager:
    """Tracks which providers are installed and creates provider instances."""

    def __init__(
        self,
        models_root: Path,
        catalog: list[CatalogEntry] | None = None,
    ) -> None:
        self._root = models_root
        self._catalog = catalog if catalog is not None else CATALOG

    def entries(self) -> list[CatalogEntry]:
        return list(self._catalog)

    def get_entry(self, provider_id: str) -> CatalogEntry | None:
        return next((e for e in self._catalog if e.id == provider_id), None)

    def is_installed(self, provider_id: str) -> bool:
        entry = self.get_entry(provider_id)
        if entry is None:
            return False
        if entry.kind == "fake":
            return True
        marker = self._root / entry.extract_subdir / ".mediamind-installed.json"
        return marker.exists()

    def mark_installed(self, provider_id: str, sha256: str | None = None) -> None:
        entry = self.get_entry(provider_id)
        if entry is None:
            raise ValueError(f"Unknown provider: {provider_id}")
        marker = self._root / entry.extract_subdir / ".mediamind-installed.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({"installed_at": time.time(), "sha256": sha256}),
            encoding="utf-8",
        )

    def create(self, provider_id: str) -> FaceProvider:
        entry = self.get_entry(provider_id)
        if entry is None:
            raise ValueError(f"Unknown provider: {provider_id}")
        if entry.kind == "fake":
            from mediamind.providers.fake import FakeColorProvider
            return FakeColorProvider()
        if not self.is_installed(provider_id):
            raise RuntimeError(f"Provider '{provider_id}' is not installed — download it first")
        if entry.kind == "insightface_pack":
            from mediamind.providers.insightface_provider import InsightFaceProvider
            pack_name = entry.id.replace("insightface-", "").replace("-", "_")
            return InsightFaceProvider(pack=pack_name, root=str(self._root))
        if entry.kind == "opencv_zoo":
            from mediamind.providers.opencv_provider import OpenCVYuNetSFaceProvider
            model_dir = self._root / entry.extract_subdir
            return OpenCVYuNetSFaceProvider(model_dir)
        raise ValueError(f"Unsupported provider kind: {entry.kind}")
