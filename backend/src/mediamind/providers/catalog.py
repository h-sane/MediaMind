"""Static provider catalog.

Stored as Python data (not a JSON file) to simplify PyInstaller bundling —
no resource file to collect. Every entry must have a matching implementation
in providers/ or be kind='fake'.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DownloadFile:
    url: str
    sha256: str | None    # None = skip verification (pin real hash before release)
    filename: str         # target filename under the extract directory
    size_bytes: int = 0   # approximate download size for progress display


@dataclass(frozen=True)
class LicenseInfo:
    name: str
    url: str
    commercial_use: bool
    summary: str


@dataclass(frozen=True)
class CatalogEntry:
    id: str               # must match the provider's .id attribute
    name: str
    description: str
    license: LicenseInfo
    downloads: list[DownloadFile]     # empty for kind='fake'
    archive: str                      # "zip" | "direct" | "none"
    extract_subdir: str               # relative to models_dir(), e.g. "models/buffalo_l"
    embedding_dim: int
    cluster_eps: float                # DBSCAN eps tuned per model
    kind: str                         # "insightface_pack" | "opencv_zoo" | "fake"


CATALOG: list[CatalogEntry] = [
    CatalogEntry(
        id="opencv-yunet-sface",
        name="OpenCV YuNet + SFace",
        description=(
            "Lightweight face detection (YuNet, ~241 KB) + recognition (SFace, ~37 MB) "
            "from the OpenCV model zoo. Apache-2.0 licensed — free for commercial use."
        ),
        license=LicenseInfo(
            name="Apache-2.0",
            url="https://github.com/opencv/opencv_zoo",
            commercial_use=True,
            summary=(
                "Apache-2.0 — free to use in commercial and open-source projects. "
                "No restrictions on deployment or distribution."
            ),
        ),
        downloads=[
            DownloadFile(
                url="https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
                sha256=None,
                filename="face_detection_yunet_2023mar.onnx",
                size_bytes=241_000,
            ),
            DownloadFile(
                url="https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
                sha256=None,
                filename="face_recognition_sface_2021dec.onnx",
                size_bytes=38_000_000,
            ),
        ],
        archive="direct",
        extract_subdir="models/opencv-yunet-sface",
        embedding_dim=128,
        cluster_eps=0.5,
        kind="opencv_zoo",
    ),
    CatalogEntry(
        id="insightface-buffalo-l",
        name="InsightFace buffalo_l",
        description=(
            "High-accuracy face detection + recognition (SCRFD-10G + ArcFace R50). "
            "CPU-friendly. Particularly strong on Asian faces (Glint360K training)."
        ),
        license=LicenseInfo(
            name="Non-commercial research",
            url="https://github.com/deepinsight/insightface/tree/master/model_zoo",
            commercial_use=False,
            summary=(
                "These model weights are licensed for non-commercial research use only. "
                "Using them in a commercial product or service is not permitted."
            ),
        ),
        downloads=[
            DownloadFile(
                url="https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
                sha256=None,   # TODO M8: pin real sha256 after manual download
                filename="buffalo_l.zip",
                size_bytes=288_000_000,  # ~275 MB
            )
        ],
        archive="zip",
        extract_subdir="models/buffalo_l",
        embedding_dim=512,
        cluster_eps=0.5,
        kind="insightface_pack",
    ),
]
