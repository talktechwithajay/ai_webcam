"""Deciding what (if anything) to announce, and delivering it to Home Assistant.

Only structured events leave this program: a message_key from a closed vocabulary, a
sanitised person name, and (for owner-written messages only) a validated custom_text.
No images or embeddings are ever sent.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from .config import HomeAssistantCfg
from .db import MESSAGE_RE, NAME_RE

log = logging.getLogger("ahv.announce")

# Mirrors the templates in homeassistant/automation_visitor_announce.yaml (used to show
# in the dashboard what was / would be said).
TEMPLATES = {
    "test_announcement": "This is a test announcement from the home visitor system.",
    "front_door_recognised": "{name} is at the front door.",
    "front_door_unknown": "Unknown visitor at the front door.",
    "front_door_face_not_visible": "Person detected at the front door. Face not visible.",
    "welcome_home": "Welcome home, {name}.",
    "custom_message": "{text}",
    "camera_offline": "A camera is offline. Please check the system.",
    "system_health_warning": "Home visitor system health warning. Please check the dashboard.",
}
HEALTH_KEYS = {"camera_offline", "system_health_warning"}


@dataclass
class Decision:
    status: str  # send | muted | quiet_hours | cooldown | none
    key: str | None = None
    name: str | None = None
    text: str | None = None

    @property
    def message(self) -> str | None:
        if not self.key:
            return None
        return TEMPLATES[self.key].format(name=self.name or "", text=self.text or "")


def in_quiet_hours(settings: dict, now_local: datetime) -> bool:
    if not settings["quiet_hours_enabled"]:
        return False
    cur = now_local.strftime("%H:%M")
    start, end = settings["quiet_start"], settings["quiet_end"]
    if start == end:
        return False
    return (start <= cur < end) if start < end else (cur >= start or cur < end)


def decide(role: str, person, settings: dict, active_message: str | None, now_local: datetime,
           last_announced: datetime | None, cooldown_seconds: int) -> Decision:
    """Pure decision function: person is a db row with name/status/muted."""
    enrolled = person["status"] == "enrolled"
    if role == "front":
        if enrolled:
            d = Decision("send", "front_door_recognised", person["name"])
        elif settings["announce_unknown_front"]:
            d = Decision("send", "front_door_unknown")
        else:
            return Decision("none")
    else:  # indoor: only enrolled people are greeted
        if not enrolled or not settings["welcome_enabled"]:
            return Decision("none")
        if active_message:
            d = Decision("send", "custom_message", person["name"], active_message)
        else:
            d = Decision("send", "welcome_home", person["name"])
    if settings["global_mute"] or person["muted"]:
        return Decision("muted", d.key, d.name, d.text)
    if in_quiet_hours(settings, now_local):
        return Decision("quiet_hours", d.key, d.name, d.text)
    if last_announced and (now_local.astimezone(timezone.utc) - last_announced.astimezone(timezone.utc)) < timedelta(seconds=cooldown_seconds):
        return Decision("cooldown", d.key, d.name, d.text)
    return d


def confidence_category(score: float | None) -> str:
    if score is None:
        return "none"
    return "high" if score >= 0.6 else "medium" if score >= 0.45 else "low"


def build_event(key: str, name: str | None, camera: str, confidence: str, text: str | None = None) -> dict:
    if key not in TEMPLATES:
        raise ValueError(f"unknown message_key {key!r}")
    if name is not None and not NAME_RE.match(name):
        raise ValueError("invalid person name")
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": key,
        "person_name": name,
        "camera_id": camera,
        "confidence_category": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_key": key,
    }
    if key == "custom_message":
        if not text or not MESSAGE_RE.match(text):
            raise ValueError("invalid custom_text")
        event["custom_text"] = text
    return event


class Announcer:
    """Sends events to Home Assistant on a background thread so camera loops never block."""

    def __init__(self, ha: HomeAssistantCfg, dry_run_getter: Callable[[], bool]):
        self.ha = ha
        self._dry_run = dry_run_getter
        self._q: queue.Queue = queue.Queue(maxsize=100)
        self.last_result: dict | None = None
        self._t = threading.Thread(target=self._run, name="announcer", daemon=True)
        self._t.start()

    def submit(self, decision: Decision, camera: str, confidence: str,
               on_done: Callable[[str, str | None], None] | None = None) -> None:
        try:
            self._q.put_nowait((decision, camera, confidence, on_done))
        except queue.Full:
            log.error("announcement queue full, dropping %s", decision.key)
            if on_done:
                on_done("failed", decision.message)

    def send_now(self, decision: Decision, camera: str, confidence: str) -> str:
        """Synchronous variant (used by the dashboard 'test' button and tests)."""
        return self._deliver(decision, camera, confidence)

    def _run(self) -> None:
        while True:
            decision, camera, confidence, on_done = self._q.get()
            try:
                status = self._deliver(decision, camera, confidence)
                if on_done:
                    on_done(status, decision.message)
            except Exception:
                log.exception("announcement failed")
            finally:
                self._q.task_done()

    def drain(self, timeout: float = 5.0) -> bool:
        """Wait until queued announcements were delivered (used by tests and shutdown)."""
        end = time.time() + timeout
        while self._q.unfinished_tasks and time.time() < end:
            time.sleep(0.01)
        return not self._q.unfinished_tasks

    def _deliver(self, decision: Decision, camera: str, confidence: str) -> str:
        try:
            event = build_event(decision.key, decision.name, camera, confidence, decision.text)
        except ValueError as e:
            log.error("refusing to send invalid event: %s", e)
            return self._record("failed")
        if self._dry_run():
            log.info("[dry-run] would announce: %s", decision.message)
            return self._record("dry_run")
        if not self.ha.enabled or not self.ha.webhook_id:
            return self._record("disabled")
        req = urllib.request.Request(
            f"{self.ha.base_url.rstrip('/')}/api/webhook/{self.ha.webhook_id}",
            data=json.dumps(event).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.ha.timeout_seconds):
                pass
            return self._record("sent")
        except urllib.error.HTTPError as e:  # never log the URL: it contains the webhook secret
            log.error("Home Assistant returned HTTP %s", e.code)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log.error("Home Assistant unreachable: %s", e.__class__.__name__)
        return self._record("failed")

    def _record(self, status: str) -> str:
        self.last_result = {"status": status, "at": datetime.now(timezone.utc).isoformat()}
        return status
