# PyInstaller spec for the MediaMind engine (backend).
#
# Build:
#   cd backend
#   pyinstaller mediamind.spec
#
# Output:
#   backend/dist/mediamind/         (one-dir mode, preferred for startup speed)
#     mediamind.exe
#     _internal/                    (DLLs, .pyd, collected packages)
#
# The Electron main process reads MEDIAMIND_ENGINE_PATH from its environment
# (set by electron-builder extraResources) and falls back to the system Python
# if not set (dev mode).

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files for packages that need non-Python resources.
datas = []
datas += collect_data_files("insightface", excludes=["**/__pycache__"])
datas += collect_data_files("onnxruntime", excludes=["**/__pycache__"])

# Hidden imports needed because dynamic imports aren't always detected.
hiddenimports = [
    # FastAPI / Starlette internals
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "starlette.routing",
    "starlette.middleware",
    "anyio",
    "anyio._backends._asyncio",
    # ML stack
    "sklearn",
    "sklearn.cluster",
    "sklearn.neighbors",
    "sklearn.utils",
    "sklearn.utils._cython_blas",
    "sklearn.neighbors._typedefs",
    "sklearn.neighbors._quad_tree",
    "sklearn.tree._utils",
    # OpenCV
    "cv2",
    # InsightFace
    "insightface",
    "insightface.app",
    "insightface.model_zoo",
    # ONNX Runtime
    "onnxruntime",
    "onnxruntime.capi",
    "onnxruntime.capi.onnxruntime_inference_collection",
    # Image handling
    "PIL",
    "PIL.Image",
    # Mediamind itself (all submodules)
    "mediamind",
    "mediamind.api",
    "mediamind.api.app",
    "mediamind.api.routes.libraries",
    "mediamind.api.routes.scans",
    "mediamind.api.routes.duplicates",
    "mediamind.api.routes.providers",
    "mediamind.api.routes.persons",
    "mediamind.api.routes.organize",
    "mediamind.api.routes.pending",
    "mediamind.api.routes.multi_person",
    "mediamind.providers.insightface_provider",
    "mediamind.providers.opencv_provider",
]
hiddenimports += collect_submodules("mediamind")

a = Analysis(
    ["src/mediamind/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "test", "tests", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mediamind",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # backend is a server, not a GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="mediamind",
)
