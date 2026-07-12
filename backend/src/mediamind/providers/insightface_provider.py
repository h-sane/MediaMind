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

import numpy as np

from mediamind.providers.base import DetectedFace


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
