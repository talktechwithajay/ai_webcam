"""Face detection, embedding and matching.

Models (both run locally on CPU through OpenCV's DNN module, no extra packages):
  * YuNet  face detector   (OpenCV Zoo, MIT licence)
  * SFace  face embedding  (OpenCV Zoo, Apache-2.0 licence for the model code/weights)
Download them with:  python tools/download_models.py
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"


@dataclass
class Face:
    x: int
    y: int
    w: int
    h: int
    score: float
    raw: np.ndarray | None = None  # detector row, needed for alignment

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def size(self) -> int:
        return min(self.w, self.h)


class FaceEngine(Protocol):
    def detect(self, frame: np.ndarray) -> list[Face]: ...

    def embed(self, frame: np.ndarray, face: Face) -> np.ndarray: ...


class OpenCVFaceEngine:
    def __init__(self, models_dir: Path, detect_score: float = 0.85):
        det, rec = Path(models_dir) / YUNET_FILE, Path(models_dir) / SFACE_FILE
        for p in (det, rec):
            if not p.exists():
                raise FileNotFoundError(f"{p} missing. Run: python tools/download_models.py")
        self._det = cv2.FaceDetectorYN.create(str(det), "", (320, 320), detect_score, 0.3, 5000)
        self._rec = cv2.FaceRecognizerSF.create(str(rec), "")
        self._lock = threading.Lock()  # the OpenCV objects are not thread-safe

    def detect(self, frame: np.ndarray) -> list[Face]:
        h, w = frame.shape[:2]
        with self._lock:
            self._det.setInputSize((w, h))
            _, rows = self._det.detect(frame)
        faces = []
        for r in rows if rows is not None else []:
            x, y, fw, fh = (int(round(v)) for v in r[:4])
            x, y = max(0, x), max(0, y)
            fw, fh = min(fw, w - x), min(fh, h - y)
            if fw > 0 and fh > 0:
                faces.append(Face(x, y, fw, fh, float(r[14]), r))
        return faces

    def embed(self, frame: np.ndarray, face: Face) -> np.ndarray:
        with self._lock:
            aligned = self._rec.alignCrop(frame, face.raw)
            feat = self._rec.feature(aligned)
        return normalise(feat)


def normalise(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return v / n if n else v


class Matcher:
    """Cosine-similarity matching against stored templates (cached, refreshed when templates change)."""

    def __init__(self, store, threshold: float):
        self.store = store
        self.threshold = threshold
        self._version = -1
        self._ids: np.ndarray = np.zeros(0, dtype=np.int64)
        self._status: list[str] = []
        self._mat: np.ndarray = np.zeros((0, 128), dtype=np.float32)

    def _refresh(self) -> None:
        if self._version == self.store.templates_version:
            return
        rows = self.store.load_templates()
        self._ids = np.array([r[0] for r in rows], dtype=np.int64)
        self._status = [r[1] for r in rows]
        self._mat = np.stack([normalise(r[2]) for r in rows]) if rows else np.zeros((0, 128), dtype=np.float32)
        self._version = self.store.templates_version

    def match(self, emb: np.ndarray, enrolled_only: bool = False) -> tuple[int | None, float]:
        """Best person above threshold, or (None, best_score)."""
        self._refresh()
        if not len(self._ids):
            return None, 0.0
        sims = self._mat @ normalise(emb)
        if enrolled_only:
            mask = np.array([s == "enrolled" for s in self._status])
            if not mask.any():
                return None, 0.0
            sims = np.where(mask, sims, -1.0)
        i = int(np.argmax(sims))
        best = float(sims[i])
        return (int(self._ids[i]), best) if best >= self.threshold else (None, best)
