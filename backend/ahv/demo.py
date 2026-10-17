"""Synthetic demo data (cartoon portraits, no real faces) for trying the dashboard."""
from __future__ import annotations

import random
import zlib
from datetime import timedelta

import cv2
import numpy as np

from .db import Store, now_utc
from .pipeline import jpeg


def portrait(seed: int, label: str = "") -> bytes:
    rng = random.Random(seed)
    bg = tuple(rng.randint(60, 200) for _ in range(3))
    img = np.full((240, 200, 3), bg, np.uint8)
    skin = (rng.randint(120, 200), rng.randint(140, 190), rng.randint(170, 230))
    cv2.ellipse(img, (100, 130), (60, 75), 0, 0, 360, skin, -1)
    cv2.circle(img, (78, 115), 7, (30, 30, 30), -1)
    cv2.circle(img, (122, 115), 7, (30, 30, 30), -1)
    cv2.ellipse(img, (100, 160), (22, 10), 0, 0, 180, (40, 40, 120), 3)
    cv2.putText(img, label[:14], (8, 232), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return jpeg(img)


def seed_demo(store: Store, days: int = 14, seed: int = 7) -> int:
    rng = random.Random(seed)
    emb = lambda: np.array([rng.gauss(0, 1) for _ in range(128)], dtype=np.float32)  # noqa: E731
    named = {"Naresh": store.create_person("Naresh"), "Aryan": store.create_person("Aryan"), "Meera": store.create_person("Meera")}
    unknowns = [store.create_person(None) for _ in range(4)]
    n = 0
    base = now_utc()
    for i in range(days * 3):
        when = base - timedelta(days=rng.randint(0, days - 1), hours=rng.randint(0, 20), minutes=rng.randint(0, 59))
        group = rng.random()
        if group < 0.5:
            name = rng.choice(list(named))
            pid, cam, label, conf = named[name], rng.choice(["front_door", "indoor"]), name, rng.uniform(0.5, 0.8)
        else:
            idx = rng.randrange(len(unknowns))
            pid, cam, label, conf = unknowns[idx], "front_door", f"Visitor {idx + 1}", None
        vid = store.add_visit(pid, cam, when, conf, portrait(zlib.crc32(label.encode()) % 1000 + i, label),
                              portrait(zlib.crc32(label.encode()) % 1000 + i, label), emb())
        store.update_visit_announce(vid, "dry_run", f"{label} is at the front door." if cam == "front_door" else f"Welcome home, {label}.")
        n += 1
    store.save_message(named["Naresh"], "Welcome Naresh, today please make Aloo Paratha!")
    return n
