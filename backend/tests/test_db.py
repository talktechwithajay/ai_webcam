from datetime import date, datetime, timedelta, timezone

import pytest

from ahv.db import ValidationError, now_utc
from conftest import vec


def add(store, pid, camera="front_door", when=None, seed=1):
    return store.add_visit(pid, camera, when or now_utc(), None, b"jpegbytes", b"thumb", vec(seed))


def test_images_and_embeddings_are_encrypted_on_disk(store):
    pid = store.create_person()
    vid = add(store, pid)
    files = list(store.image_dir.rglob("*.enc"))
    assert files and all(b"jpegbytes" not in f.read_bytes() for f in files)
    assert store.visit_image(vid) == b"jpegbytes"
    assert store.visit_image(vid, thumb=True) == b"thumb"


def test_naming_unknown_renames_all_past_visits(store):
    pid = store.create_person()
    ids = [add(store, pid, when=now_utc() - timedelta(days=d)) for d in range(5)]
    assert all(v["label"] == "UNKNOWN #1" for v in store.query_visits()["items"])
    store.name_person(pid, "Naresh")
    items = store.query_visits()["items"]
    assert len(items) == 5 and {v["label"] for v in items} == {"Naresh"}
    assert {v["id"] for v in items} == set(ids)
    assert {v["status"] for v in items} == {"enrolled"}
    # renaming again updates every visit again
    store.name_person(pid, "Naresh Kumar")
    assert {v["label"] for v in store.query_visits()["items"]} == {"Naresh Kumar"}


def test_name_validation_and_duplicates(store):
    a, b = store.create_person(), store.create_person()
    with pytest.raises(ValidationError):
        store.name_person(a, "<script>")
    with pytest.raises(ValidationError):
        store.name_person(a, "UNKNOWN 5")
    store.name_person(a, "Aryan")
    with pytest.raises(ValidationError):
        store.name_person(b, "aryan")  # case-insensitive clash


def test_unknown_numbering_and_merge(store):
    u1, u2 = store.create_person(), store.create_person()
    assert store.get_person(u2)["unknown_no"] == 2
    known = store.create_person("Meera")
    add(store, u1)
    add(store, u2)
    store.add_template(u1, vec(10))
    merged = store.merge_people(u1, known)
    assert merged["visit_count"] == 1 and store.get_person(u1) is None
    assert any(pid == known for pid, _, _ in store.load_templates())
    with pytest.raises(ValidationError):
        store.merge_people(known, u2)  # cannot merge a named person into an unknown one


def test_date_filter_uses_local_days(store):
    now = now_utc()
    pid = store.create_person()
    add(store, pid, when=now)
    add(store, pid, when=now - timedelta(days=3))
    add(store, pid, when=now - timedelta(days=10))
    today = now.astimezone().date()
    assert store.query_visits(today, today)["total"] == 1
    assert store.query_visits(today - timedelta(days=5), today)["total"] == 2
    assert store.query_visits(None, today - timedelta(days=5))["total"] == 1
    assert store.query_visits()["total"] == 3
    assert [v["ts"] for v in store.query_visits(order="asc")["items"]] == sorted(v["ts"] for v in store.query_visits()["items"])


def test_kind_and_person_filters(store):
    k, u = store.create_person("Aryan"), store.create_person()
    add(store, k)
    add(store, u)
    assert store.query_visits(kind="known")["total"] == 1
    assert store.query_visits(kind="unknown")["total"] == 1
    assert store.query_visits(person_id=k)["total"] == 1


def test_retention_deletes_only_old_unknown(store):
    u, k = store.create_person(), store.create_person("Aryan")
    old = now_utc() - timedelta(days=100)
    old_unknown = add(store, u, when=old)
    new_unknown = add(store, u, when=now_utc() - timedelta(days=10))
    old_known = add(store, k, when=old)
    assert store.retention_candidates(90) == [old_unknown]
    assert store.purge_unknown_older_than(90) == 1
    ids = {v["id"] for v in store.query_visits()["items"]}
    assert ids == {new_unknown, old_known}
    assert store.visit_image(old_unknown) is None


def test_retention_removes_person_when_last_visit_purged(store):
    u = store.create_person()
    add(store, u, when=now_utc() - timedelta(days=200))
    store.add_template(u, vec(3))
    store.purge_unknown_older_than(90)
    assert store.get_person(u) is None and store.load_templates() == []


def test_settings_defaults_and_validation(store):
    s = store.get_settings()
    assert s["retention_days"] == 90 and s["dry_run"] is True and s["global_mute"] is False
    assert store.update_settings({"retention_days": "never"})["retention_days"] == "never"
    assert store.update_settings({"retention_days": 30})["retention_days"] == 30
    for bad in ({"retention_days": 0}, {"retention_days": "abc"}, {"retention_days": 99999}, {"nope": 1},
                {"quiet_start": "25:00"}, {"global_mute": "yes"}):
        with pytest.raises(ValidationError):
            store.update_settings(bad)


def test_messages_schedule_and_validation(store):
    p = store.create_person("Naresh")
    u = store.create_person()
    mid = store.save_message(p, "Welcome Naresh, today please make Aloo Paratha!")
    assert store.active_message(p, date.today()) == "Welcome Naresh, today please make Aloo Paratha!"
    with pytest.raises(ValidationError):
        store.save_message(u, "hello")  # unknown people cannot have messages
    with pytest.raises(ValidationError):
        store.save_message(p, "<b>hi</b>")
    store.save_message(p, "Monday special", weekdays=[0])
    monday = date(2026, 10, 19)
    assert monday.weekday() == 0
    assert store.active_message(p, monday) == "Monday special"  # newest matching wins
    assert store.active_message(p, date(2026, 10, 20)) == "Welcome Naresh, today please make Aloo Paratha!"
    store.save_message(p, "Vacation", start_date="2026-12-01", end_date="2026-12-31")
    assert store.active_message(p, date(2026, 12, 5)) == "Vacation"
    store.save_message(p, "Updated", message_id=mid, enabled=False)
    assert store.active_message(p, date(2026, 10, 20)) is None
    store.delete_message(mid)


def test_assign_visit_split_and_move(store):
    a, b = store.create_person("Aryan"), store.create_person()
    v = add(store, b, seed=5)
    moved = store.assign_visit(v, a)
    assert moved["visit_count"] == 1 and store.get_person(b) is None  # emptied unknown removed
    split = store.assign_visit(v, None)
    assert split["status"] == "unknown" and split["visit_count"] == 1


def test_delete_person_and_range_guard(store):
    p = store.create_person("Aryan")
    add(store, p)
    with pytest.raises(ValidationError):
        store.delete_visits_in_range(None, None)
    assert store.delete_person(p) == 1
    assert store.query_visits()["total"] == 0 and not list(store.image_dir.rglob("*.enc"))


def test_template_dedupe_and_cap(store):
    p = store.create_person("Aryan")
    assert store.add_template(p, vec(1), max_templates=3)
    assert not store.add_template(p, vec(1), max_templates=3)  # near-identical
    for s in (2, 3, 4):
        store.add_template(p, vec(s), max_templates=3)
    assert len(store.load_templates()) == 3
