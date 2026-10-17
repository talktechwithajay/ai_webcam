import base64
from datetime import date, timedelta

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from ahv.announce import Announcer
from ahv.api import Auth, create_app
from ahv.config import HomeAssistantCfg
from ahv.db import now_utc
from conftest import FakeEngine, vec


@pytest.fixture
def client(cfg, store, vault):
    announcer = Announcer(HomeAssistantCfg(enabled=False), lambda: True)
    app = create_app(cfg, store, Auth(cfg, vault), announcer, FakeEngine(), None)
    c = TestClient(app)
    assert c.post("/api/login", json={"username": "admin", "password": "s3cret-pass"}).status_code == 200
    return c


def seed(store, n=3, status_name=None, days_ago=0, camera="front_door"):
    pid = store.create_person(status_name)
    for i in range(n):
        store.add_visit(pid, camera, now_utc() - timedelta(days=days_ago, minutes=i), None, b"img", b"th", vec(i + 1))
    return pid


def test_requires_login(cfg, store, vault):
    c = TestClient(create_app(cfg, store, Auth(cfg, vault), Announcer(HomeAssistantCfg(), lambda: True)))
    for path in ("/api/visits", "/api/people", "/api/settings", "/api/status", "/api/visits/1/image"):
        assert c.get(path).status_code == 401
    assert c.post("/api/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert c.get("/api/me").json()["signed_in"] is False


def test_login_lockout_after_repeated_failures(cfg, store, vault):
    c = TestClient(create_app(cfg, store, Auth(cfg, vault), Announcer(HomeAssistantCfg(), lambda: True)))
    codes = [c.post("/api/login", json={"username": "admin", "password": "x"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    assert c.post("/api/login", json={"username": "admin", "password": "s3cret-pass"}).status_code == 429


def test_forged_cookie_rejected(cfg, store, vault):
    c = TestClient(create_app(cfg, store, Auth(cfg, vault), Announcer(HomeAssistantCfg(), lambda: True)))
    c.cookies.set("ahv_session", "abc.def")
    assert c.get("/api/visits").status_code == 401


def test_visit_list_with_date_filter_and_pictures(client, store):
    seed(store, 2, days_ago=0)
    seed(store, 2, days_ago=5)
    today = date.today().isoformat()
    r = client.get("/api/visits", params={"date_from": today, "date_to": today}).json()
    assert r["total"] == 2
    vid = r["items"][0]["id"]
    img = client.get(f"/api/visits/{vid}/image")
    assert img.status_code == 200 and img.content == b"img" and img.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/visits/{vid}/image?thumb=true").content == b"th"
    assert client.get("/api/visits", params={"date_from": "garbage"}).status_code == 422
    assert client.get("/api/visits", params={"kind": "bogus"}).status_code == 422


def test_name_unknown_updates_all_visits_via_api(client, store):
    pid = seed(store, 4)
    assert {v["label"] for v in client.get("/api/visits").json()["items"]} == {"UNKNOWN #1"}
    r = client.post(f"/api/people/{pid}/name", json={"name": "Naresh"})
    assert r.status_code == 200 and r.json()["label"] == "Naresh" and r.json()["status"] == "enrolled"
    assert {v["label"] for v in client.get("/api/visits").json()["items"]} == {"Naresh"}
    assert client.post(f"/api/people/{pid}/name", json={"name": "<b>"}).status_code == 422
    assert client.post("/api/people/999/name", json={"name": "Zed"}).status_code == 404


def test_visitors_page_data_and_per_person_table(client, store):
    a, b = seed(store, 3, "Aryan"), seed(store, 1)
    people = client.get("/api/people").json()
    by = {p["label"]: p for p in people}
    assert by["Aryan"]["visit_count"] == 3 and by["UNKNOWN #1"]["visit_count"] == 1
    assert by["Aryan"]["thumb_visit_id"] and by["Aryan"]["first_seen"] <= by["Aryan"]["last_seen"]
    assert [p["label"] for p in client.get("/api/people", params={"status": "unknown"}).json()] == ["UNKNOWN #1"]
    assert len(client.get("/api/people", params={"q": "ary"}).json()) == 1
    rows = client.get("/api/visits", params={"person_id": a, "order": "asc"}).json()
    assert rows["total"] == 3 and all(v["label"] == "Aryan" for v in rows["items"])


def test_settings_retention_default_never_and_preview(client, store):
    assert client.get("/api/settings").json()["retention_days"] == 90
    seed(store, 2, days_ago=120)
    seed(store, 1, days_ago=1)
    assert client.get("/api/retention/preview").json() == {"would_delete": 2, "days": 90}
    assert client.get("/api/retention/preview", params={"days": 200}).json()["would_delete"] == 0
    assert client.put("/api/settings", json={"retention_days": "never"}).json()["retention_days"] == "never"
    assert client.post("/api/retention/run").json()["deleted"] == 0
    assert client.get("/api/visits").json()["total"] == 3
    client.put("/api/settings", json={"retention_days": 30})
    assert client.post("/api/retention/run").json()["deleted"] == 2
    assert client.put("/api/settings", json={"retention_days": -5}).status_code == 422


def test_messages_crud_and_mutes(client, store):
    pid = seed(store, 1, "Naresh")
    r = client.post("/api/messages", json={"person_id": pid, "text": "Welcome Naresh, today please make Aloo Paratha!"})
    assert r.status_code == 200
    mid = r.json()["id"]
    assert client.post("/api/messages", json={"person_id": pid, "text": "{{ x }}"}).status_code == 422
    assert client.put(f"/api/messages/{mid}", json={"person_id": pid, "text": "Chai please", "enabled": False}).json()["enabled"] is False
    assert len(client.get("/api/messages", params={"person_id": pid}).json()) == 1
    assert client.patch(f"/api/people/{pid}", json={"muted": True}).json()["muted"] is True
    assert client.post("/api/mute-all", json={"muted": True}).json()["global_mute"] is True
    assert client.delete(f"/api/messages/{mid}").status_code == 200
    assert client.delete(f"/api/messages/{mid}").status_code == 404


def test_merge_split_and_delete(client, store):
    named = seed(store, 1, "Aryan")
    unk = seed(store, 2)
    merged = client.post(f"/api/people/{unk}/merge", json={"target_id": named}).json()
    assert merged["visit_count"] == 3
    vid = client.get("/api/visits", params={"person_id": named}).json()["items"][0]["id"]
    split = client.post(f"/api/visits/{vid}/assign", json={}).json()
    assert split["status"] == "unknown"
    assert client.delete(f"/api/visits/{vid}").status_code == 200
    assert client.post("/api/visits/delete-range", json={}).status_code == 422
    assert client.delete(f"/api/people/{named}").json()["deleted_visits"] == 2


def test_enroll_from_photo(client, store):
    from conftest import make_frame

    frame = make_frame(33)
    ok, buf = cv2.imencode(".png", frame)
    b64 = base64.b64encode(buf.tobytes()).decode()
    body = {"name": "Naresh", "photos": [b64], "consent_confirmed": True}
    assert client.post("/api/people", json={**body, "consent_confirmed": False}).status_code == 422
    r = client.post("/api/people", json=body)
    assert r.status_code == 200 and r.json()["label"] == "Naresh"
    assert client.post("/api/people", json={**body, "photos": ["!!!"]}).status_code == 422
    two_faces = base64.b64encode(cv2.imencode(".png", make_frame(1, 2))[1].tobytes()).decode()
    assert client.post("/api/people", json={"name": "Meera", "photos": [two_faces], "consent_confirmed": True}).status_code == 422


def test_status_and_test_announcement(client):
    s = client.get("/api/status").json()
    assert s["dry_run"] is True and s["recognition_ready"] is True and s["stats"]["visits"] == 0
    assert client.post("/api/test-announcement").json() == {"status": "dry_run"}


def test_security_headers(client):
    h = client.get("/api/me").headers
    assert h["x-frame-options"] == "DENY" and "default-src 'self'" in h["content-security-policy"]
