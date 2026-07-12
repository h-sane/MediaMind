"""Static provider catalog.

Stored as Python data (not a JSON file) to simplify PyInstaller bundling —
no resource file to collect. Every entry must have a matching implementation
in providers/ or be kind='fake'.

Provenance rule: download URLs come ONLY from the two trusted upstream
repositories (github.com/deepinsight/insightface releases and
github.com/opencv/opencv_zoo) so licensing and origin stay verifiable.
Never guess a URL — every entry below was verified against the live release
asset (HTTP 200 + exact Content-Length) before being added.

Ordering matters: when a face scan is started without an explicit provider,
the API falls back to the FIRST installed entry in this list — so entries are
ordered by preference, not by size.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    extract_subdir: str               # relative to the entry's install root,
                                      # e.g. "models/buffalo_l" (see
                                      # ProviderManager.root_for)
    embedding_dim: int
    cluster_eps: float                # DBSCAN eps tuned per model
    kind: str                         # "insightface_pack" | "opencv_zoo" | "fake"
    # Filenames that must exist in the model dir for the entry to count as
    # installed (the files the provider actually loads). Empty = derived from
    # `downloads` for archive="direct" entries.
    required_files: tuple[str, ...] = ()


# All InsightFace model-zoo packs share one license: the weights are for
# non-commercial research use only (stated on the model_zoo page itself).
_INSIGHTFACE_LICENSE = LicenseInfo(
    name="Non-commercial research",
    url="https://github.com/deepinsight/insightface/tree/master/model_zoo",
    commercial_use=False,
    summary=(
        "These model weights are licensed for non-commercial research use only. "
        "Using them in a commercial product or service is not permitted."
    ),
)


CATALOG: list[CatalogEntry] = [
    CatalogEntry(
        id="opencv-yunet-sface",
        name="OpenCV YuNet + SFace",
        description=(
            "Lightweight face detection (YuNet, ~241 KB) + recognition (SFace, ~37 MB) "
            "from the OpenCV model zoo. Apache-2.0 licensed — the only option here "
            "that is free for commercial use. Best when you need a small download "
            "or commercial-safe licensing."
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
            "High-accuracy face detection + recognition (SCRFD-10G + ArcFace "
            "ResNet-50 trained on WebFace600K). CPU-friendly. The best all-round "
            "choice for large photo libraries where accuracy matters most."
        ),
        license=_INSIGHTFACE_LICENSE,
        downloads=[
            DownloadFile(
                url="https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
                sha256="80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f",
                filename="buffalo_l.zip",
                size_bytes=288_621_354,
            )
        ],
        archive="zip",
        extract_subdir="models/buffalo_l",
        embedding_dim=512,
        cluster_eps=0.5,
        kind="insightface_pack",
        required_files=("det_10g.onnx", "w600k_r50.onnx"),
    ),
    CatalogEntry(
        id="insightface-antelopev2",
        name="InsightFace antelopev2",
        description=(
            "Maximum-accuracy recognition (ArcFace ResNet-100 trained on "
            "Glint360K) with SCRFD-10G detection. The largest and slowest "
            "option — best when matching quality matters more than scan speed."
        ),
        license=_INSIGHTFACE_LICENSE,
        downloads=[
            DownloadFile(
                url="https://github.com/deepinsight/insightface/releases/download/v0.7/antelopev2.zip",
                sha256="8e182f14fc6e80b3bfa375b33eb6cff7ee05d8ef7633e738d1c89021dcf0c5c5",
                filename="antelopev2.zip",
                size_bytes=360_662_982,
            )
        ],
        archive="zip",
        extract_subdir="models/antelopev2",
        embedding_dim=512,
        cluster_eps=0.5,
        kind="insightface_pack",
        required_files=("scrfd_10g_bnkps.onnx", "glintr100.onnx"),
    ),
    CatalogEntry(
        id="insightface-buffalo-m",
        name="InsightFace buffalo_m",
        description=(
            "Medium buffalo pack: the same recognition model as buffalo_l "
            "(ArcFace ResNet-50, WebFace600K) with a lighter SCRFD-2.5G "
            "detector. Nearly buffalo_l accuracy with faster face detection — "
            "a good middle ground for medium-to-large libraries."
        ),
        license=_INSIGHTFACE_LICENSE,
        downloads=[
            DownloadFile(
                url="https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_m.zip",
                sha256="d98264bd8f2dc75cbc2ddce2a14e636e02bb857b3051c234b737bf3b614edca9",
                filename="buffalo_m.zip",
                size_bytes=275_951_529,
            )
        ],
        archive="zip",
        extract_subdir="models/buffalo_m",
        embedding_dim=512,
        cluster_eps=0.5,
        kind="insightface_pack",
        required_files=("det_2.5g.onnx", "w600k_r50.onnx"),
    ),
    CatalogEntry(
        id="insightface-buffalo-sc",
        name="InsightFace buffalo_sc",
        description=(
            "Smallest and fastest InsightFace pack (~15 MB): compact SCRFD-500M "
            "detection + MobileFaceNet recognition. Lower accuracy than the "
            "bigger packs — best for a quick first try, previews, or "
            "low-spec machines."
        ),
        license=_INSIGHTFACE_LICENSE,
        downloads=[
            DownloadFile(
                url="https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_sc.zip",
                sha256="57d31b56b6ffa911c8a73cfc1707c73cab76efe7f13b675a05223bf42de47c72",
                filename="buffalo_sc.zip",
                size_bytes=14_969_382,
            )
        ],
        archive="zip",
        extract_subdir="models/buffalo_sc",
        embedding_dim=512,
        cluster_eps=0.5,
        kind="insightface_pack",
        required_files=("det_500m.onnx", "w600k_mbf.onnx"),
    ),
]
