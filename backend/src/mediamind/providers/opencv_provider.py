"""OpenCV YuNet + SFace provider — Apache-2.0 licensed, commercially usable.

YuNet detects face bounding boxes and 5 landmark points.
SFace aligns the crop to those landmarks, then computes a 128-dim embedding.

Both models ship from the OpenCV model zoo (opencv/opencv_zoo on GitHub).
Requires opencv-contrib-python >= 4.5.4 (FaceDetectorYN + FaceRecognizerSF).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mediamind.providers.base import DetectedFace

YUNET_MODEL = "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = "face_recognition_sface_2021dec.onnx"


class OpenCVYuNetSFaceProvider:
    """YuNet face detection + SFace recognition from the OpenCV model zoo."""

    id = "opencv-yunet-sface"
    embedding_dim = 128

    def __init__(self, model_dir: Path) -> None:
        self._det_path = model_dir / YUNET_MODEL
        self._rec_path = model_dir / SFACE_MODEL
        self._detector = None
        self._recognizer = None

    def prepare(self) -> None:
        if self._detector is not None:
            return
        import cv2

        if not hasattr(cv2, "FaceDetectorYN"):
            raise RuntimeError(
                "FaceDetectorYN not available — install opencv-contrib-python >= 4.5.4"
            )
        if not hasattr(cv2, "FaceRecognizerSF"):
            raise RuntimeError(
                "FaceRecognizerSF not available — install opencv-contrib-python >= 4.5.4"
            )

        if not self._det_path.exists():
            raise FileNotFoundError(f"YuNet model not found: {self._det_path}")
        if not self._rec_path.exists():
            raise FileNotFoundError(f"SFace model not found: {self._rec_path}")

        # Create detector with a placeholder size; setInputSize() is called per frame.
        self._detector = cv2.FaceDetectorYN.create(
            model=str(self._det_path),
            config="",
            input_size=(320, 320),
            score_threshold=0.6,
            nms_threshold=0.3,
            top_k=5000,
        )
        self._recognizer = cv2.FaceRecognizerSF.create(
            model=str(self._rec_path),
            config="",
        )

    def get_faces(self, frame_bgr: np.ndarray) -> list[DetectedFace]:
        assert self._detector is not None and self._recognizer is not None, \
            "prepare() must be called first"

        h, w = frame_bgr.shape[:2]
        self._detector.setInputSize((w, h))

        retval, detections = self._detector.detect(frame_bgr)

        if retval == 0 or detections is None:
            return []

        faces: list[DetectedFace] = []
        for det in detections:
            x, y, bw, bh = float(det[0]), float(det[1]), float(det[2]), float(det[3])
            x1 = max(0.0, x)
            y1 = max(0.0, y)
            x2 = min(float(w), x + bw)
            y2 = min(float(h), y + bh)

            if x2 <= x1 or y2 <= y1:
                continue

            try:
                face_align = self._recognizer.alignCrop(frame_bgr, det)
                raw = self._recognizer.feature(face_align)
                embedding = np.asarray(raw, dtype=np.float32).flatten()
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
            except Exception:
                continue

            faces.append(DetectedFace(bbox=(x1, y1, x2, y2), embedding=embedding))

        return faces
