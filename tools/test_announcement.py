"""Send a schema-validated test event to the Home Assistant webhook (stdlib only).

Usage:
    python tools/test_announcement.py --generate-id          # print a new random webhook ID
    python tools/test_announcement.py                        # send a test announcement
    python tools/test_announcement.py --key front_door_recognised --name Aryan

Reads HA_BASE_URL and HA_WEBHOOK_ID from the environment or a .env file in the
repo root. The webhook ID is a secret: it is never printed or logged here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Closed vocabulary: Home Assistant only speaks templates it owns, selected by message_key.
MESSAGE_KEYS = {
    "test_announcement",
    "front_door_recognised",
    "front_door_unknown",
    "front_door_face_not_visible",
    "welcome_home",
    "custom_message",
    "camera_offline",
    "system_health_warning",
}
CONFIDENCE = {"high", "medium", "low", "none"}
NAME_RE = re.compile(r"^[\w .'\-]{1,40}$", re.UNICODE)
MESSAGE_RE = re.compile(r"^[\w .,!?:'\-]{1,200}$", re.UNICODE)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def build_event(key: str, name: str | None, camera: str, confidence: str, text: str | None = None) -> dict:
    if key not in MESSAGE_KEYS:
        raise ValueError(f"unknown message_key {key!r}")
    if confidence not in CONFIDENCE:
        raise ValueError(f"bad confidence {confidence!r}")
    if name is not None and not NAME_RE.match(name):
        raise ValueError("person_name must be 1-40 chars: letters, digits, space . ' -")
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
            raise ValueError("custom text must be 1-200 chars: letters, digits, space . , ! ? : ' -")
        event["custom_text"] = text
    return event


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--generate-id", action="store_true")
    ap.add_argument("--key", default="test_announcement")
    ap.add_argument("--name")
    ap.add_argument("--text", help="spoken text for --key custom_message")
    ap.add_argument("--camera", default="front_door")
    ap.add_argument("--confidence", default="none")
    ap.add_argument("--dry-run", action="store_true", help="validate and print payload, send nothing")
    args = ap.parse_args()

    if args.generate_id:
        print("ahv_" + secrets.token_urlsafe(32))
        return 0

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    try:
        event = build_event(args.key, args.name, args.camera, args.confidence, args.text)
    except ValueError as e:
        sys.exit(f"Invalid event: {e}")
    if args.dry_run:
        print(json.dumps(event, indent=2))
        return 0

    base = os.environ.get("HA_BASE_URL", "").rstrip("/")
    hook = os.environ.get("HA_WEBHOOK_ID", "")
    if not base or not hook:
        sys.exit("Set HA_BASE_URL and HA_WEBHOOK_ID in .env (see .env.example).")

    req = urllib.request.Request(
        f"{base}/api/webhook/{hook}",
        data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"HTTP {resp.status} - event {event['event_id']} accepted by Home Assistant")
            print("This only proves HA received it. Confirm the Echo Dot actually spoke.")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from Home Assistant (webhook ID wrong, or local_only blocked the caller)")
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f"Could not reach Home Assistant at {base}: {e.__class__.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
