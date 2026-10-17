"""Camera sources: CP Plus DVR/NVR (RTSP), generic RTSP, USB webcam, or a test file.

LatestFrameReader keeps a background thread draining the stream so consumers always get
the newest frame (no growing lag), reconnects with backoff, and flags stale streams.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import CameraCfg, Config, ConfigError, mask_url

log = logging.getLogger("ahv.camera")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}
CV_PARAMS = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000]


@dataclass
class Frame:
    image: np.ndarray
    ts: float
    seq: int


def open_capture(cfg: Config, cam: CameraCfg, subtype: int | None = None):
    """Open a cv2.VideoCapture for this camera. Returns (capture, is_static_image_array|None)."""
    if cam.source in ("recorder", "rtsp"):
        return cv2.VideoCapture(cfg.camera_url(cam, subtype), cv2.CAP_FFMPEG, CV_PARAMS), None
    if cam.source == "usb":
        return cv2.VideoCapture(cam.usb_index, cv2.CAP_DSHOW), None
    if cam.source == "file":
        p = Path(cam.path)
        if p.suffix.lower() in IMAGE_SUFFIXES:
            img = cv2.imread(str(p))
            if img is None:
                raise ConfigError(f"cannot read image {p}")
            return None, img
        return cv2.VideoCapture(str(p)), None
    raise ConfigError(f"camera {cam.id} has no source")


def grab_hires(cfg: Config, cam: CameraCfg, settle_frames: int = 6) -> np.ndarray | None:
    """Fetch one full-resolution frame from the recorder (only used when a person is confirmed)."""
    if cam.source != "recorder" or cam.snapshot_subtype == cam.detect_subtype:
        return None
    cap = None
    try:
        cap, _ = open_capture(cfg, cam, cam.snapshot_subtype)
        if not cap or not cap.isOpened():
            return None
        frame = None
        for _ in range(settle_frames):  # first frames can be stale/partial after connect
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
        return frame
    except Exception as e:  # network/decoder errors must never kill the pipeline
        log.warning("hires grab failed for %s: %s", cam.id, mask_url(str(e)))
        return None
    finally:
        if cap:
            cap.release()


class LatestFrameReader(threading.Thread):
    def __init__(self, cfg: Config, cam: CameraCfg):
        super().__init__(name=f"cam-{cam.id}", daemon=True)
        self.cfg, self.cam = cfg, cam
        self._halt = threading.Event()
        self._lock = threading.Lock()
        self._frame: Frame | None = None
        self._seq = 0
        self.state = "connecting"  # connecting | online | offline
        self.error = ""
        self.offline_since: float | None = time.time()
        self._fps_count, self._fps_t0, self.fps = 0, time.time(), 0.0

    # --- consumer API
    def latest(self) -> Frame | None:
        with self._lock:
            return self._frame

    def status(self) -> dict:
        f = self.latest()
        return {
            "id": self.cam.id, "label": self.cam.label, "role": self.cam.role, "source": self.cam.source,
            "state": self.state, "error": self.error, "fps": round(self.fps, 1),
            "frame_age_s": round(time.time() - f.ts, 1) if f else None,
            "size": list(f.image.shape[1::-1]) if f else None,
        }

    def stop(self) -> None:
        self._halt.set()

    # --- thread body
    def run(self) -> None:
        backoff = 1.0
        while not self._halt.is_set():
            try:
                cap, static = open_capture(self.cfg, self.cam)
            except Exception as e:
                self._set_offline(mask_url(str(e)))
                self._halt.wait(backoff := min(backoff * 2, 30))
                continue
            if static is not None:
                self._serve_static(static)
                return
            if not cap or not cap.isOpened():
                self._set_offline("cannot open stream (check IP, port, credentials, channel, RTSP enabled)")
                if cap:
                    cap.release()
                self._halt.wait(backoff := min(backoff * 2, 30))
                continue
            backoff = 1.0
            try:
                self._drain(cap)
            finally:
                cap.release()
            self._halt.wait(1.0)

    def _drain(self, cap) -> None:
        is_file = self.cam.source == "file"
        fps = cap.get(cv2.CAP_PROP_FPS) or 25 if is_file else 0
        last_ok = time.time()
        while not self._halt.is_set():
            ok, img = cap.read()
            if not ok or img is None:
                if is_file:  # loop test video
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    if time.time() - last_ok > 5:
                        return
                    continue
                self._set_offline("stream stopped delivering frames")
                return
            last_ok = time.time()
            self._publish(img)
            if is_file:
                self._halt.wait(1.0 / fps)

    def _serve_static(self, img: np.ndarray) -> None:
        while not self._halt.is_set():
            self._publish(img.copy())
            self._halt.wait(0.2)

    def _publish(self, img: np.ndarray) -> None:
        self._seq += 1
        with self._lock:
            self._frame = Frame(img, time.time(), self._seq)
        if self.state != "online":
            log.info("camera %s online", self.cam.id)
        self.state, self.error, self.offline_since = "online", "", None
        self._fps_count += 1
        now = time.time()
        if now - self._fps_t0 >= 2:
            self.fps, self._fps_count, self._fps_t0 = self._fps_count / (now - self._fps_t0), 0, now

    def _set_offline(self, reason: str) -> None:
        if self.state != "offline":
            log.warning("camera %s offline: %s", self.cam.id, reason)
        if self.offline_since is None:
            self.offline_since = time.time()
        self.state, self.error = "offline", reason
