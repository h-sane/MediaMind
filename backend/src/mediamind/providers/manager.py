"""Provider manager: installed-state tracking and provider factory.

Lives on app.state.providers. Tests inject a ProviderManager with a custom
catalog, a tmp models_root, and a tmp insightface_root — no model download
needed.

Install locations
-----------------
- ``insightface_pack`` entries live in the InsightFace package's own default
  cache (``~/.insightface``). InsightFace auto-downloads there itself, other
  tools (including the V0 prototype) already populate it, and sharing it means
  a multi-hundred-MB pack is only ever stored once on the user's disk.
- All other kinds (``opencv_zoo``) live in MediaMind's private models dir
  (``config.models_dir()``) — they have no external cache convention.

Installed-state truth
---------------------
"Installed" means the actual model files exist on disk. The
``.mediamind-installed.json`` marker is bookkeeping metadata only (when it was
downloaded, with what hash) — deleting the real model files makes the provider
downloadable again even if the marker survives, and model files that arrived
outside MediaMind (e.g. InsightFace's own auto-download) count as installed
without any marker.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from mediamind.providers.base import FaceProvider
from mediamind.providers.catalog import CATALOG, CatalogEntry

MARKER_FILENAME = ".mediamind-installed.json"


def default_insightface_root() -> Path:
    """The insightface package's own default model cache root."""
    return Path.home() / ".insightface"


class ProviderManager:
    """Tracks which providers are installed and creates provider instances."""

    def __init__(
        self,
        models_root: Path,
        catalog: list[CatalogEntry] | None = None,
        insightface_root: Path | None = None,
    ) -> None:
        self._root = models_root
        self._insightface_root = (
            insightface_root if insightface_root is not None else default_insightface_root()
        )
        self._catalog = catalog if catalog is not None else CATALOG

    def entries(self) -> list[CatalogEntry]:
        return list(self._catalog)

    def get_entry(self, provider_id: str) -> CatalogEntry | None:
        return next((e for e in self._catalog if e.id == provider_id), None)

    def root_for(self, entry: CatalogEntry) -> Path:
        """Base directory this entry installs under (see module docstring)."""
        if entry.kind == "insightface_pack":
            return self._insightface_root
        return self._root

    def model_dir(self, entry: CatalogEntry) -> Path:
        return self.root_for(entry) / entry.extract_subdir

    @staticmethod
    def _required_files(entry: CatalogEntry) -> list[str]:
        """Filenames that must exist in model_dir for the entry to be installed."""
        if entry.required_files:
            return list(entry.required_files)
        if entry.archive == "direct":
            # Direct downloads land in model_dir under their own filenames.
            return [dl.filename for dl in entry.downloads]
        return []

    def is_installed(self, provider_id: str) -> bool:
        entry = self.get_entry(provider_id)
        if entry is None:
            return False
        if entry.kind == "fake":
            return True
        model_dir = self.model_dir(entry)
        required = self._required_files(entry)
        if required:
            # The real files are the source of truth: present without a marker
            # (e.g. InsightFace's own cache) counts; a marker without the files
            # (user deleted them) does not.
            return all((model_dir / name).is_file() for name in required)
        # No known file list for this entry — fall back to the marker.
        return (model_dir / MARKER_FILENAME).exists()

    def mark_installed(self, provider_id: str, sha256: str | None = None) -> None:
        """Record download bookkeeping. Metadata only — not the install truth."""
        entry = self.get_entry(provider_id)
        if entry is None:
            raise ValueError(f"Unknown provider: {provider_id}")
        marker = self.model_dir(entry) / MARKER_FILENAME
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
            # Shared root: FaceAnalysis(root=X) loads X/models/<pack> — the same
            # place is_installed() just verified the .onnx files exist, so
            # InsightFace will never trigger its own surprise download here.
            return InsightFaceProvider(
                pack=pack_name,
                root=str(self._insightface_root),
                embedding_dim=entry.embedding_dim,
            )
        if entry.kind == "opencv_zoo":
            from mediamind.providers.opencv_provider import OpenCVYuNetSFaceProvider
            return OpenCVYuNetSFaceProvider(self.model_dir(entry))
        raise ValueError(f"Unsupported provider kind: {entry.kind}")
