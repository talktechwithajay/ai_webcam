"""FastAPI application: JSON API for the dashboard + static frontend."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import secrets
import time
from datetime import date, datetime, timezone
from typing import Optional

import cv2
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import __version__
from .announce import Announcer, Decision
from .config import Config
from .crypto import Vault
from .db import Store, ValidationError, now_utc
from .faces import FaceEngine
from .pipeline import Supervisor, crop_head, jpeg

log = logging.getLogger("ahv.api")
COOKIE = "ahv_session"


# ----------------------------------------------------------------------------- auth
class Auth:
    def __init__(self, cfg: Config, vault: Vault):
        self.cfg = cfg
        self.secret = vault.session_secret()
        self._fails: dict[str, list[float]] = {}

    def check_credentials(self, username: str, password: str, ip: str) -> bool:
        window = [t for t in self._fails.get(ip, []) if time.time() - t < 300]
        self._fails[ip] = window
        if len(window) >= 5:
            raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
        ok_user = hmac.compare_digest(username.encode(), self.cfg.dashboard.username.encode())
        ok_pass = hmac.compare_digest(password.encode(), self.cfg.dashboard.password.encode())
        if ok_user and ok_pass:
            self._fails.pop(ip, None)
            return True
        window.append(time.time())
        return False

    def make_token(self) -> str:
        exp = int(time.time() + self.cfg.dashboard.session_hours * 3600)
        payload = base64.urlsafe_b64encode(f"{self.cfg.dashboard.username}|{exp}".encode()).decode()
        sig = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def valid(self, token: str | None) -> bool:
        if not token or "." not in token:
            return False
        payload, sig = token.rsplit(".", 1)
        good = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return False
        try:
            user, exp = base64.urlsafe_b64decode(payload.encode()).decode().split("|")
            return int(exp) > time.time() and user == self.cfg.dashboard.username
        except (ValueError, binascii.Error):
            return False


# --------------------------------------------------------------------------- bodies
class LoginBody(BaseModel):
    username: str
    password: str


class NameBody(BaseModel):
    name: str


class PersonPatch(BaseModel):
    name: Optional[str] = None
    muted: Optional[bool] = None


class MergeBody(BaseModel):
    target_id: int


class AssignBody(BaseModel):
    person_id: Optional[int] = None  # None = split into a new unknown person


class EnrollBody(BaseModel):
    name: str
    photos: list[str] = Field(min_length=1, max_length=10)  # base64 JPEG/PNG
    consent_confirmed: bool = False


class MessageBody(BaseModel):
    person_id: int
    text: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    weekdays: list[int] = []
    enabled: bool = True


class DeleteRangeBody(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    person_id: Optional[int] = None


class MuteAllBody(BaseModel):
    muted: bool


def _date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(422, f"Invalid date {s!r}, expected YYYY-MM-DD")


# ----------------------------------------------------------------------------- app
def create_app(cfg: Config, store: Store, auth: Auth, announcer: Announcer,
               engine: FaceEngine | None = None, supervisor: Supervisor | None = None) -> FastAPI:
    app = FastAPI(title="AI Home Visitor", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        )
        return resp

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, e: ValidationError):
        return JSONResponse({"detail": str(e)}, status_code=422)

    @app.exception_handler(KeyError)
    async def _missing(_: Request, e: KeyError):
        return JSONResponse({"detail": str(e.args[0]) if e.args else "not found"}, status_code=404)

    def require_auth(request: Request) -> None:
        if not auth.valid(request.cookies.get(COOKIE)):
            raise HTTPException(401, "Not signed in")

    protected = [Depends(require_auth)]

    # --- session
    @app.post("/api/login")
    def login(body: LoginBody, request: Request, response: Response):
        ip = request.client.host if request.client else "?"
        if not auth.check_credentials(body.username, body.password, ip):
            raise HTTPException(401, "Wrong username or password")
        response.set_cookie(COOKIE, auth.make_token(), httponly=True, samesite="strict",
                            max_age=cfg.dashboard.session_hours * 3600)
        return {"ok": True}

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(request: Request):
        return {"signed_in": auth.valid(request.cookies.get(COOKIE)), "username": cfg.dashboard.username}

    # --- status
    @app.get("/api/status", dependencies=protected)
    def status():
        s = store.get_settings()
        return {
            "version": __version__,
            "cameras": supervisor.camera_status() if supervisor else [],
            "stats": store.stats(),
            "recognition_ready": engine is not None,
            "home_assistant_enabled": cfg.home_assistant.enabled,
            "dry_run": s["dry_run"],
            "global_mute": s["global_mute"],
            "last_announcement": announcer.last_result,
        }

    # --- visits
    @app.get("/api/visits", dependencies=protected)
    def visits(date_from: str | None = None, date_to: str | None = None, camera: str | None = None,
               person_id: int | None = None, kind: str = "all", limit: int = 50, offset: int = 0,
               order: str = "desc"):
        return store.query_visits(_date(date_from), _date(date_to), camera, person_id, kind, limit, offset, order)

    @app.get("/api/visits/{visit_id}/image", dependencies=protected)
    def visit_image(visit_id: int, thumb: bool = False):
        data = store.visit_image(visit_id, thumb)
        if data is None:
            raise HTTPException(404, "No picture")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    @app.delete("/api/visits/{visit_id}", dependencies=protected)
    def delete_visit(visit_id: int):
        if not store.delete_visits([visit_id]):
            raise HTTPException(404, "visit not found")
        return {"deleted": 1}

    @app.post("/api/visits/delete-range", dependencies=protected)
    def delete_range(body: DeleteRangeBody):
        return {"deleted": store.delete_visits_in_range(_date(body.date_from), _date(body.date_to), body.person_id)}

    @app.post("/api/visits/{visit_id}/assign", dependencies=protected)
    def assign_visit(visit_id: int, body: AssignBody):
        return store.assign_visit(visit_id, body.person_id, cfg.recognition.max_templates_per_person)

    # --- people
    @app.get("/api/people", dependencies=protected)
    def people(status: str | None = None, q: str | None = None):
        if status not in (None, "enrolled", "unknown"):
            raise HTTPException(422, "status must be enrolled or unknown")
        return store.list_people(status, q)

    @app.get("/api/people/{person_id}", dependencies=protected)
    def person(person_id: int):
        p = store.person_detail(person_id)
        if not p:
            raise HTTPException(404, "person not found")
        return p

    @app.post("/api/people/{person_id}/name", dependencies=protected)
    def name_person(person_id: int, body: NameBody):
        """Name an unknown person (or rename). Every past and future visit follows automatically."""
        return store.name_person(person_id, body.name)

    @app.patch("/api/people/{person_id}", dependencies=protected)
    def patch_person(person_id: int, body: PersonPatch):
        if body.name is not None:
            store.name_person(person_id, body.name)
        if body.muted is not None:
            store.set_muted(person_id, body.muted)
        return store.person_detail(person_id)

    @app.post("/api/people/{person_id}/merge", dependencies=protected)
    def merge(person_id: int, body: MergeBody):
        return store.merge_people(person_id, body.target_id)

    @app.delete("/api/people/{person_id}", dependencies=protected)
    def delete_person(person_id: int):
        return {"deleted_visits": store.delete_person(person_id)}

    @app.post("/api/people", dependencies=protected)
    def enroll(body: EnrollBody):
        """Enrol a named person from uploaded photos (exactly one face per photo)."""
        if engine is None:
            raise HTTPException(503, "Face models not installed. Run: python tools/download_models.py")
        if not body.consent_confirmed:
            raise ValidationError("Confirm that this person has agreed to be recognised")
        name = body_name = body.name
        embeddings, crops = [], []
        for i, b64 in enumerate(body.photos, 1):
            try:
                raw = base64.b64decode(b64.split(",")[-1], validate=True)
            except (binascii.Error, ValueError):
                raise ValidationError(f"Photo {i} is not valid base64")
            if len(raw) > 8_000_000:
                raise ValidationError(f"Photo {i} is larger than 8 MB")
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ValidationError(f"Photo {i} is not a readable image")
            faces = engine.detect(img)
            if len(faces) != 1:
                raise ValidationError(f"Photo {i} must contain exactly one face (found {len(faces)})")
            embeddings.append(engine.embed(img, faces[0]))
            crops.append(crop_head(img, faces[0]))
        with store.lock:
            pid = store.create_person(body_name)
            for emb in embeddings:
                store.add_template(pid, emb, cfg.recognition.max_templates_per_person)
            store.add_visit(pid, "enrollment", now_utc(), None, jpeg(crops[0]), jpeg(crops[0], 80, 160), embeddings[0])
        return store.person_detail(pid)

    @app.post("/api/mute-all", dependencies=protected)
    def mute_all(body: MuteAllBody):
        """Switch announcements off/on for everyone (also sets each person's own mute flag when muting)."""
        store.update_settings({"global_mute": body.muted})
        return store.get_settings()

    # --- indoor messages
    @app.get("/api/messages", dependencies=protected)
    def messages(person_id: int | None = None):
        return store.list_messages(person_id)

    @app.post("/api/messages", dependencies=protected)
    def create_message(body: MessageBody):
        mid = store.save_message(body.person_id, body.text, body.start_date, body.end_date, body.weekdays, body.enabled)
        return next(m for m in store.list_messages(body.person_id) if m["id"] == mid)

    @app.put("/api/messages/{message_id}", dependencies=protected)
    def update_message(message_id: int, body: MessageBody):
        store.save_message(body.person_id, body.text, body.start_date, body.end_date, body.weekdays, body.enabled, message_id)
        return next(m for m in store.list_messages(body.person_id) if m["id"] == message_id)

    @app.delete("/api/messages/{message_id}", dependencies=protected)
    def delete_message(message_id: int):
        store.delete_message(message_id)
        return {"ok": True}

    # --- settings & retention
    @app.get("/api/settings", dependencies=protected)
    def get_settings():
        return store.get_settings()

    @app.put("/api/settings", dependencies=protected)
    def put_settings(changes: dict):
        return store.update_settings(changes)

    @app.get("/api/retention/preview", dependencies=protected)
    def retention_preview(days: str | None = None):
        d = days if days is not None else store.get_settings()["retention_days"]
        if d == "never":
            return {"would_delete": 0, "days": "never"}
        try:
            n = int(d)
        except (TypeError, ValueError):
            raise HTTPException(422, "days must be a number or 'never'")
        return {"would_delete": len(store.retention_candidates(n)), "days": n}

    @app.post("/api/retention/run", dependencies=protected)
    def retention_run():
        d = store.get_settings()["retention_days"]
        if d == "never":
            return {"deleted": 0, "days": "never"}
        return {"deleted": store.purge_unknown_older_than(d), "days": d}

    @app.post("/api/test-announcement", dependencies=protected)
    def test_announcement():
        status_ = announcer.send_now(Decision("send", "test_announcement"), "dashboard", "none")
        return {"status": status_}

    # --- cameras
    @app.get("/api/cameras/{cam_id}/snapshot.jpg", dependencies=protected)
    def snapshot(cam_id: str):
        r = supervisor.readers.get(cam_id) if supervisor else None
        f = r.latest() if r else None
        if f is None:
            raise HTTPException(404, "No frame available")
        return Response(jpeg(f.image, 80, 1280), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/cameras/{cam_id}/preview.mjpg", dependencies=protected)
    def preview(cam_id: str):
        r = supervisor.readers.get(cam_id) if supervisor else None
        if r is None:
            raise HTTPException(404, "Unknown or disabled camera")

        def gen():
            last = 0
            for _ in range(60 * 30):  # at most ~30 minutes per connection
                f = r.latest()
                if f and f.seq != last:
                    last = f.seq
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg(f.image, 70, 960) + b"\r\n"
                time.sleep(0.5)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    # --- static frontend (built Vue app)
    dist = cfg.frontend_dir
    if dist.exists():
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app
