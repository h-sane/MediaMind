"""InsightFace provider — the V0 engine behind the FaceProvider interface.

Wraps `FaceAnalysis` (detection + recognition modules) for any InsightFace
model pack (buffalo_sc/m/l, antelopev2, ...). The default `buffalo_l` pack
pairs SCRFD-10G detection with ArcFace ResNet-50 recognition trained on
WebFace600K; antelopev2 uses ResNet-100 trained on Glint360K. NOTE: all
InsightFace model-zoo weights are licensed for non-commercial research use
only — the provider catalog must surface this before download.

Requires the `faces` extra (insightface + onnxruntime).
"""

from __future__ import annotations

import logging
import os

import numpy as np

from mediamind.providers.base import DetectedFace

logger = logging.getLogger("mediamind.providers.insightface")


def _scan_thread_budget() -> int:
    """How many CPU threads a scan may use, leaving headroom so the single
    backend process can still serve browsing/thumbnail requests for the app's
    other tabs while a scan runs. Reserve `MEDIAMIND_SCAN_RESERVED_CORES`
    (default 2) logical cores; never drop below 1."""
    reserved = int(os.environ.get("MEDIAMIND_SCAN_RESERVED_CORES", "2"))
    return max(1, (os.cpu_count() or 4) - reserved)


def _apply_cpu_budget() -> None:
    """Cap the two things a face scan otherwise lets run wild across every
    core — ONNX Runtime inference and OpenCV image decoding — so a scan can't
    starve the request-serving threads in the same process. Idempotent and
    fully defensive: any failure here must never stop a scan from running.

    ONNX Runtime defaults `intra_op_num_threads` to 0 (= all cores) and
    InsightFace exposes no way to pass SessionOptions, so we inject a
    thread-capped SessionOptions into the one place it builds sessions."""
    n = _scan_thread_budget()
    try:
        import cv2

        cv2.setNumThreads(n)
    except Exception:
        pass
    try:
        import onnxruntime as ort
        from insightface.model_zoo import model_zoo as mz

        if getattr(mz.PickableInferenceSession, "_mm_thread_capped", False):
            return
        orig_init = mz.PickableInferenceSession.__init__

        def _capped_init(self, model_path, **kwargs):
            if "sess_options" not in kwargs:
                so = ort.SessionOptions()
                so.intra_op_num_threads = n
                so.inter_op_num_threads = n
                kwargs["sess_options"] = so
            orig_init(self, model_path, **kwargs)

        mz.PickableInferenceSession.__init__ = _capped_init
        mz.PickableInferenceSession._mm_thread_capped = True
        logger.info("Face-scan CPU budget: %d threads (of %d cores)", n, os.cpu_count() or 0)
    except Exception as exc:
        logger.warning("Could not cap ONNX Runtime threads (scan may use all cores): %s", exc)


class InsightFaceProvider:
    def __init__(
        self,
        pack: str = "buffalo_l",
        ctx_id: int = -1,
        det_size: int = 640,
        root: str | None = None,
        embedding_dim: int = 512,
    ):
        self.id = f"insightface-{pack.replace('_', '-')}"
        self.embedding_dim = embedding_dim
        self._pack = pack
        self._ctx_id = ctx_id  # -1 = CPU
        self._det_size = det_size
        self._root = root  # model weights directory; None = InsightFace default (~/.insightface)
        self._app = None

    def prepare(self) -> None:
        if self._app is not None:
            return
        _apply_cpu_budget()
        from insightface.app import FaceAnalysis

        kwargs = dict(name=self._pack, allowed_modules=["detection", "recognition"])
        if self._root is not None:
            kwargs["root"] = self._root
        self._app = FaceAnalysis(**kwargs)
        self._app.prepare(ctx_id=self._ctx_id, det_size=(self._det_size, self._det_size))

    def get_faces(self, frame_bgr: np.ndarray) -> list[DetectedFace]:
        assert self._app is not None, "prepare() must be called first"
        faces = []
        for f in self._app.get(frame_bgr):
            if f.normed_embedding is None:
                continue
            x1, y1, x2, y2 = (float(v) for v in f.bbox)
            faces.append(DetectedFace(bbox=(x1, y1, x2, y2), embedding=f.normed_embedding))
        return faces
