import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ahv.announce import Announcer, Decision, build_event, decide, in_quiet_hours
from ahv.config import HomeAssistantCfg
from ahv.db import SETTING_DEFAULTS


def settings(**kw):
    base = {"global_mute": False, "quiet_hours_enabled": True, "quiet_start": "22:00", "quiet_end": "07:00",
            "announce_unknown_front": True, "welcome_enabled": True}
    return {**base, **kw}


def person(status="enrolled", name="Naresh", muted=False):
    return {"status": status, "name": name, "muted": muted}


NOON = datetime(2026, 10, 19, 12, 0).astimezone()
NIGHT = datetime(2026, 10, 19, 23, 30).astimezone()
EARLY = datetime(2026, 10, 19, 6, 0).astimezone()


def test_quiet_hours_wrap_midnight():
    s = settings()
    assert in_quiet_hours(s, NIGHT) and in_quiet_hours(s, EARLY) and not in_quiet_hours(s, NOON)
    assert not in_quiet_hours(settings(quiet_hours_enabled=False), NIGHT)


def test_front_door_known_unknown():
    d = decide("front", person(), settings(), None, NOON, None, 60)
    assert (d.status, d.key, d.message) == ("send", "front_door_recognised", "Naresh is at the front door.")
    d = decide("front", person("unknown", None), settings(), None, NOON, None, 60)
    assert (d.status, d.key) == ("send", "front_door_unknown")
    assert decide("front", person("unknown", None), settings(announce_unknown_front=False), None, NOON, None, 60).status == "none"


def test_indoor_custom_message_and_welcome():
    d = decide("indoor", person(), settings(), "Welcome Naresh, today please make Aloo Paratha!", NOON, None, 1800)
    assert d.key == "custom_message" and d.message == "Welcome Naresh, today please make Aloo Paratha!"
    d = decide("indoor", person(), settings(), None, NOON, None, 1800)
    assert d.key == "welcome_home" and d.message == "Welcome home, Naresh."
    assert decide("indoor", person("unknown", None), settings(), None, NOON, None, 1800).status == "none"
    assert decide("indoor", person(), settings(welcome_enabled=False), None, NOON, None, 1800).status == "none"


def test_mutes_quiet_hours_and_cooldown():
    assert decide("indoor", person(muted=True), settings(), None, NOON, None, 60).status == "muted"
    assert decide("indoor", person(), settings(global_mute=True), None, NOON, None, 60).status == "muted"
    assert decide("front", person(), settings(), None, NIGHT, None, 60).status == "quiet_hours"
    recent = NOON.astimezone(timezone.utc) - timedelta(seconds=30)
    assert decide("front", person(), settings(), None, NOON, recent, 60).status == "cooldown"
    old = NOON.astimezone(timezone.utc) - timedelta(seconds=300)
    assert decide("front", person(), settings(), None, NOON, old, 60).status == "send"


def test_event_validation_blocks_injection():
    e = build_event("custom_message", "Naresh", "indoor", "high", "Hello there!")
    assert e["custom_text"] == "Hello there!" and e["message_key"] == "custom_message"
    for args in (("rm_rf", None, "x", "none"), ("front_door_recognised", "bad{{name}}", "x", "none"),
                 ("custom_message", "Naresh", "x", "none", "{{ states('x') }}"), ("custom_message", "N", "x", "none", None)):
        with pytest.raises(ValueError):
            build_event(*args)


class _Hook(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Hook.received.append((self.path, json.loads(body)))
        self.send_response(200 if self.path.endswith("good") else 404)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def ha_server():
    _Hook.received = []
    srv = HTTPServer(("127.0.0.1", 0), _Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_announcer_sends_webhook_and_reports_status(ha_server):
    ok = Announcer(HomeAssistantCfg(enabled=True, base_url=ha_server, webhook_id="good"), lambda: False)
    status = ok.send_now(Decision("send", "front_door_recognised", "Aryan"), "front_door", "high")
    assert status == "sent"
    path, body = _Hook.received[-1]
    assert path == "/api/webhook/good" and body["person_name"] == "Aryan" and "image" not in json.dumps(body)
    bad = Announcer(HomeAssistantCfg(enabled=True, base_url=ha_server, webhook_id="wrong"), lambda: False)
    assert bad.send_now(Decision("send", "front_door_unknown"), "front_door", "none") == "failed"


def test_announcer_dry_run_and_disabled(ha_server):
    dry = Announcer(HomeAssistantCfg(enabled=True, base_url=ha_server, webhook_id="good"), lambda: True)
    assert dry.send_now(Decision("send", "welcome_home", "Aryan"), "indoor", "high") == "dry_run"
    assert _Hook.received == []
    off = Announcer(HomeAssistantCfg(enabled=False), lambda: False)
    assert off.send_now(Decision("send", "welcome_home", "Aryan"), "indoor", "high") == "disabled"


def test_announcer_unreachable_is_failed_not_exception():
    a = Announcer(HomeAssistantCfg(enabled=True, base_url="http://127.0.0.1:9", webhook_id="x", timeout_seconds=1), lambda: False)
    assert a.send_now(Decision("send", "front_door_unknown"), "front_door", "none") == "failed"


def test_async_submit_calls_back(ha_server):
    a = Announcer(HomeAssistantCfg(enabled=True, base_url=ha_server, webhook_id="good"), lambda: False)
    done = threading.Event()
    got = {}
    a.submit(Decision("send", "welcome_home", "Aryan"), "indoor", "high",
             on_done=lambda s, m: (got.update(status=s, message=m), done.set()))
    assert done.wait(5) and got == {"status": "sent", "message": "Welcome home, Aryan."}


def test_setting_defaults_cover_decide_inputs():
    assert {"global_mute", "quiet_hours_enabled", "announce_unknown_front", "welcome_enabled"} <= set(SETTING_DEFAULTS)
