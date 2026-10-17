import time

import numpy as np
import pytest

from ahv.announce import Announcer
from ahv.camera import Frame
from ahv.config import HomeAssistantCfg
from ahv.faces import Face, Matcher
from ahv.pipeline import CameraWorker, FaceTracker, in_zone
from conftest import FakeEngine, make_frame, vec


class StubReader:
    def __init__(self):
        self.seq = 0
        self._f = None

    def push(self, image):
        self.seq += 1
        self._f = Frame(image, time.time(), self.seq)

    def latest(self):
        return self._f


@pytest.fixture
def rig(cfg, store):
    announcer = Announcer(HomeAssistantCfg(enabled=False), lambda: True)  # dry-run: nothing leaves the process
    matcher = Matcher(store, cfg.recognition.match_threshold)

    def make(cam_id):
        cam = cfg.camera(cam_id)
        reader = StubReader()
        return CameraWorker(cfg, cam, reader, FakeEngine(), store, matcher, announcer), reader

    return make


def feed(worker, reader, frame, times=3, t0=1000.0):
    created = []
    for i in range(times):
        reader.push(frame)
        created += worker.step(now=t0 + i * 0.2)
    worker.announcer.drain()
    return created


def test_tracker_requires_min_frames():
    t = FaceTracker(min_frames=3, settle_seconds=0, lost_seconds=1)
    f = Face(10, 10, 50, 50, 0.9)
    img = np.zeros((100, 100, 3), np.uint8)
    assert t.update([f], img, 0.0) == [] and t.update([f], img, 0.1) == []
    assert len(t.update([f], img, 0.2)) == 1
    assert t.update([f], img, 0.3) == []  # a confirmed track never fires twice
    assert t.update([], img, 5.0) == [] and t.tracks == []  # lost track dropped


def test_zone_filter():
    f = Face(80, 40, 20, 20, 0.9)
    assert in_zone(f, (100, 200), None)
    assert in_zone(f, (100, 200), [0.4, 0.0, 0.6, 1.0])
    assert not in_zone(f, (100, 200), [0.0, 0.0, 0.3, 1.0])


def test_unknown_front_door_visitor_is_saved_as_unknown(rig, store):
    w, r = rig("front_door")
    assert len(feed(w, r, make_frame(11))) == 1
    v = store.query_visits()["items"][0]
    assert v["label"] == "UNKNOWN #1" and v["announced"] == "dry_run"
    assert v["message"] == "Unknown visitor at the front door."
    assert store.visit_image(v["id"])  # picture saved (encrypted)


def test_two_people_together_make_two_entries(rig, store):
    w, r = rig("front_door")
    assert len(feed(w, r, make_frame(21, 22))) == 2
    items = store.query_visits()["items"]
    assert {v["label"] for v in items} == {"UNKNOWN #1", "UNKNOWN #2"}


def test_same_person_within_cooldown_is_one_visit_then_new_visit(rig, store):
    w, r = rig("front_door")
    feed(w, r, make_frame(31))
    # walks away (track lost), returns 10 s later: still the same visit
    assert feed(w, r, make_frame(31), t0=1010.0) == []
    assert store.query_visits()["total"] == 1
    # beyond the cooldown the same unknown person gets a second visit, same person id
    w.cam.log_cooldown_seconds = 0
    assert len(feed(w, r, make_frame(31), t0=1020.0)) == 1
    items = store.query_visits()["items"]
    assert len(items) == 2 and len({v["person_id"] for v in items}) == 1
    assert len(store.list_people(status="unknown")) == 1


def test_naming_unknown_then_recognised_by_name(rig, store):
    w, r = rig("front_door")
    feed(w, r, make_frame(41))
    pid = store.list_people()[0]["id"]
    store.name_person(pid, "Naresh")
    w.cam.log_cooldown_seconds = 0
    w.cam.announce_cooldown_seconds = 0
    feed(w, r, make_frame(41), t0=2000.0)
    labels = [v["label"] for v in store.query_visits()["items"]]
    assert labels == ["Naresh", "Naresh"]  # old visit renamed, new visit recognised
    assert store.query_visits()["items"][0]["message"] == "Naresh is at the front door."


def test_indoor_ignores_unknown_and_greets_enrolled_with_custom_message(rig, store):
    w, r = rig("indoor")
    assert feed(w, r, make_frame(51)) == []  # unknown indoors: ignored by default
    pid = store.create_person("Naresh")
    store.add_template(pid, vec(52))
    store.save_message(pid, "Welcome Naresh, today please make Aloo Paratha!")
    assert len(feed(w, r, make_frame(52), t0=3000.0)) == 1
    v = store.query_visits()["items"][0]
    assert v["label"] == "Naresh" and v["announced"] == "dry_run"
    assert v["message"] == "Welcome Naresh, today please make Aloo Paratha!"


def test_muted_person_is_logged_but_not_announced(rig, store):
    w, r = rig("indoor")
    pid = store.create_person("Naresh", muted=True)
    store.add_template(pid, vec(61))
    feed(w, r, make_frame(61))
    v = store.query_visits()["items"][0]
    assert v["label"] == "Naresh" and v["announced"] == "muted"


def test_global_mute_silences_everyone(rig, store):
    w, r = rig("front_door")
    store.update_settings({"global_mute": True})
    feed(w, r, make_frame(71))
    assert store.query_visits()["items"][0]["announced"] == "muted"


def test_indoor_log_unknown_setting(rig, store):
    store.update_settings({"indoor_log_unknown": True})
    w, r = rig("indoor")
    assert len(feed(w, r, make_frame(81))) == 1
    v = store.query_visits()["items"][0]
    assert v["label"].startswith("UNKNOWN") and v["announced"] == "none"


def test_different_people_are_not_confused(rig, store):
    w, r = rig("front_door")
    feed(w, r, make_frame(91))
    feed(w, r, make_frame(92), t0=1100.0)
    assert len(store.list_people(status="unknown")) == 2


def test_stale_frames_are_ignored(rig):
    w, r = rig("front_door")
    r.push(make_frame(5))
    assert w.step(now=time.time() + 60) == []
