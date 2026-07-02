"""InsightFace provider — the V0 engine behind the FaceProvider interface.

Wraps `FaceAnalysis` (detection + recognition modules). The default
`buffalo_l` pack is strong on Asian faces (Glint360K training) and runs
CPU-only. NOTE: buffalo_l model weights are licensed for non-commercial
research use — the provider catalog must surface this before download.

Requires the `faces` extra (insightface + onnxruntime).
"""

from __future__ import annotations

import numpy as np

from mediamind.providers.base import DetectedFace


class InsightFaceProvider:
    embedding_dim = 512

    def __init__(
        self,
        pack: str = "buffalo_l",
        ctx_id: int = -1,
        det_size: int = 640,
        root: str | None = None,
    ):
        self.id = f"insightface-{pack.replace('_', '-')}"
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
