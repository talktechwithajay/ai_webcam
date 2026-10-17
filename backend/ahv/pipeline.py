"""Per-camera processing: detect faces -> track -> confirm -> match -> log visit -> announce.

Every confirmed face becomes its own visit, so several people arriving together produce
several entries. A face is "confirmed" only after it has been seen in min_frames frames
and settle_seconds have passed, and the best frame of that track is the one saved.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np

from .announce import Announcer, Decision, confidence_category, decide
from .camera import LatestFrameReader, grab_hires
from .config import CameraCfg, Config
from .db import Store, now_utc
from .faces import Face, FaceEngine, Matcher

log = logging.getLogger("ahv.pipeline")


def iou(a: Face, b: Face) -> float:
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union else 0.0


@dataclass
class Track:
    id: int
    face: Face
    first_ts: float
    last_ts: float
    frames: int = 1
    committed: bool = False
    best_quality: float = 0.0
    best_face: Face | None = None
    best_frame: np.ndarray | None = None
    frame_shape: tuple[int, int] = (0, 0)  # (h, w) of the frame best_face belongs to

    def consider(self, face: Face, frame: np.ndarray) -> None:
        q = face.score * face.size
        if q > self.best_quality:
            self.best_quality, self.best_face = q, face
            self.best_frame = frame.copy()
            self.frame_shape = frame.shape[:2]


class FaceTracker:
    def __init__(self, min_frames: int, settle_seconds: float, lost_seconds: float, iou_min: float = 0.25):
        self.min_frames, self.settle, self.lost, self.iou_min = min_frames, settle_seconds, lost_seconds, iou_min
        self.tracks: list[Track] = []
        self._next = 1

    def update(self, faces: list[Face], frame: np.ndarray, now: float) -> list[Track]:
        """Feed one frame's detections. Returns tracks that just became confirmed."""
        self.tracks = [t for t in self.tracks if now - t.last_ts <= self.lost]  # drop lost tracks first
        unmatched = list(faces)
        for t in self.tracks:
            best, best_iou = None, self.iou_min
            for f in unmatched:
                v = iou(t.face, f)
                if v > best_iou:
                    best, best_iou = f, v
            if best:
                unmatched.remove(best)
                t.face, t.last_ts, t.frames = best, now, t.frames + 1
                t.consider(best, frame)
        for f in unmatched:
            t = Track(self._next, f, now, now)
            t.consider(f, frame)
            self._next += 1
            self.tracks.append(t)
        ready = [
            t for t in self.tracks
            if not t.committed and t.frames >= self.min_frames and now - t.first_ts >= self.settle
        ]
        for t in ready:
            t.committed = True
        self.tracks = [t for t in self.tracks if now - t.last_ts <= self.lost]
        return ready


def in_zone(face: Face, shape: tuple[int, int], zone: list[float] | None) -> bool:
    if not zone:
        return True
    h, w = shape
    cx, cy = face.center
    return zone[0] * w <= cx <= zone[2] * w and zone[1] * h <= cy <= zone[3] * h


def crop_head(frame: np.ndarray, face: Face, margin: float = 0.6) -> np.ndarray:
    h, w = frame.shape[:2]
    x0, y0 = max(0, int(face.x - margin * face.w)), max(0, int(face.y - margin * face.h))
    x1, y1 = min(w, int(face.x + (1 + margin) * face.w)), min(h, int(face.y + (1 + margin) * face.h))
    return frame[y0:y1, x0:x1]


def jpeg(img: np.ndarray, quality: int = 88, max_side: int | None = None) -> bytes:
    if max_side:
        s = max_side / max(img.shape[:2])
        if s < 1:
            img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return buf.tobytes()


class CameraWorker(threading.Thread):
    def __init__(self, cfg: Config, cam: CameraCfg, reader: LatestFrameReader, engine: FaceEngine,
                 store: Store, matcher: Matcher, announcer: Announcer):
        super().__init__(name=f"worker-{cam.id}", daemon=True)
        self.cfg, self.cam, self.reader, self.engine = cfg, cam, reader, engine
        self.store, self.matcher, self.announcer = store, matcher, announcer
        rc = cfg.recognition
        self.tracker = FaceTracker(rc.min_frames, rc.settle_seconds, rc.lost_seconds)
        self._halt = threading.Event()
        self._last_seq = 0
        self.last_visit_id: int | None = None
        self.last_error = ""

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        period = 1.0 / max(0.5, self.cfg.recognition.process_fps)
        while not self._halt.wait(period):
            try:
                self.step()
            except Exception as e:  # keep the camera loop alive whatever happens
                self.last_error = f"{e.__class__.__name__}: {e}"
                log.exception("camera %s: processing error", self.cam.id)

    def step(self, now: float | None = None) -> list[int]:
        """Process the newest frame once. Returns ids of visits created."""
        fr = self.reader.latest()
        now = time.time() if now is None else now
        if fr is None or fr.seq == self._last_seq or now - fr.ts > 5:
            return []
        self._last_seq = fr.seq
        rc = self.cfg.recognition
        faces = [
            f for f in self.engine.detect(fr.image)
            if f.size >= rc.min_face_px and in_zone(f, fr.image.shape[:2], self.cam.zone)
        ]
        created = []
        for track in self.tracker.update(faces, fr.image, now):
            vid = self.commit(track)
            if vid:
                created.append(vid)
        return created

    # ---------------------------------------------------------------- commit
    def commit(self, track: Track) -> int | None:
        frame, face = track.best_frame, track.best_face
        if frame is None or face is None:
            return None
        frame, face = self._refine(frame, face, track.frame_shape)
        emb = self.engine.embed(frame, face)
        cam, store = self.cam, self.store
        enrolled_only = cam.role == "indoor" and not store.get_settings()["indoor_log_unknown"]
        pid, score = self.matcher.match(emb, enrolled_only=enrolled_only)
        if pid is None and enrolled_only:
            log.debug("%s: unrecognised face ignored (indoor_log_unknown is off)", cam.id)
            return None
        ts = now_utc()
        if pid is not None:
            last = store.last_visit_time(pid, cam.id)
            if last and (ts - last).total_seconds() < cam.log_cooldown_seconds:
                return None  # same person still around: same visit
        picture = crop_head(frame, face)
        image_b, thumb_b = jpeg(picture), jpeg(picture, 80, 160)
        with store.lock:  # keep person+visit creation atomic w.r.t. the retention purge
            new_unknown = pid is None
            if new_unknown:
                pid = store.create_person(None)
            vid = store.add_visit(pid, cam.id, ts, score if not new_unknown else None, image_b, thumb_b, emb)
            person = store.get_person(pid)
            if person["status"] == "unknown":
                store.add_template(pid, emb, self.cfg.recognition.max_templates_per_person)
        self.last_visit_id = vid
        self._announce(vid, person, score if not new_unknown else None, ts)
        log.info("camera %s: visit #%s (%s)", cam.id, vid, "new unknown" if new_unknown else f"person {pid}")
        return vid

    def _refine(self, frame: np.ndarray, face: Face, shape: tuple[int, int]) -> tuple[np.ndarray, Face]:
        """Re-detect the face on the full-resolution stream for a sharper picture and embedding."""
        hires = grab_hires(self.cfg, self.cam)
        if hires is None:
            return frame, face
        sy, sx = hires.shape[0] / shape[0], hires.shape[1] / shape[1]
        cx, cy = face.center[0] * sx, face.center[1] * sy
        cands = self.engine.detect(hires)
        if not cands:
            return frame, face
        best = min(cands, key=lambda f: (f.center[0] - cx) ** 2 + (f.center[1] - cy) ** 2)
        if ((best.center[0] - cx) ** 2 + (best.center[1] - cy) ** 2) ** 0.5 > max(best.w, best.h):
            return frame, face  # the person moved away; keep the sub-stream picture
        return hires, best

    def _announce(self, visit_id: int, person, score: float | None, ts: datetime) -> None:
        store, cam = self.store, self.cam
        settings = store.get_settings()
        now_local = ts.astimezone()
        active = store.active_message(person["id"], now_local.date()) if person["status"] == "enrolled" else None
        last = store.last_visit_time(person["id"], cam.id, announced_only=True)
        d: Decision = decide(cam.role, person, settings, active, now_local, last, cam.announce_cooldown_seconds)
        if d.status != "send":
            store.update_visit_announce(visit_id, d.status, d.message)
            return
        store.update_visit_announce(visit_id, "pending", d.message)
        self.announcer.submit(
            d, cam.id, confidence_category(score),
            on_done=lambda status, msg: store.update_visit_announce(visit_id, status, msg),
        )


class Supervisor:
    """Owns readers + workers + health monitoring."""

    OFFLINE_ALERT_SECONDS = 300

    def __init__(self, cfg: Config, store: Store, engine: FaceEngine, announcer: Announcer):
        self.cfg, self.store, self.engine, self.announcer = cfg, store, engine, announcer
        self.matcher = Matcher(store, cfg.recognition.match_threshold)
        self.readers: dict[str, LatestFrameReader] = {}
        self.workers: dict[str, CameraWorker] = {}
        self._alerted: set[str] = set()
        self._halt = threading.Event()
        self._monitor: threading.Thread | None = None

    def start(self) -> None:
        for cam in self.cfg.cameras:
            if not cam.enabled:
                continue
            reader = LatestFrameReader(self.cfg, cam)
            worker = CameraWorker(self.cfg, cam, reader, self.engine, self.store, self.matcher, self.announcer)
            self.readers[cam.id], self.workers[cam.id] = reader, worker
            reader.start()
            worker.start()
        self._monitor = threading.Thread(target=self._watch, name="health", daemon=True)
        self._monitor.start()

    def stop(self) -> None:
        self._halt.set()
        for w in self.workers.values():
            w.stop()
        for r in self.readers.values():
            r.stop()

    def camera_status(self) -> list[dict]:
        out = []
        for cam in self.cfg.cameras:
            r = self.readers.get(cam.id)
            if r:
                st = r.status()
                st["last_error"] = self.workers[cam.id].last_error
                out.append(st)
            else:
                out.append({"id": cam.id, "label": cam.label, "role": cam.role, "source": cam.source,
                            "state": "disabled", "error": "", "fps": 0, "frame_age_s": None, "size": None})
        return out

    def _watch(self) -> None:
        while not self._halt.wait(30):
            for cid, r in self.readers.items():
                down = r.offline_since is not None and time.time() - r.offline_since > self.OFFLINE_ALERT_SECONDS
                if down and cid not in self._alerted:
                    self._alerted.add(cid)
                    settings = self.store.get_settings()
                    if not settings["global_mute"]:
                        self.announcer.submit(Decision("send", "camera_offline"), cid, "none")
                elif not down and cid in self._alerted and r.state == "online":
                    self._alerted.discard(cid)
