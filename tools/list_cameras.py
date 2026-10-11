"""Camera discovery / identification tool (Milestone 1).

Probes camera indices with OpenCV, reports which ones deliver frames, and can
open a live preview window per camera so you can tell which is the front-door
camera and which is the indoor camera. Indices are NOT stable on Windows, so
this is a diagnostic only: the app must store the chosen index in configuration.

Usage:
    python tools/list_cameras.py                 # probe indices 0-9
    python tools/list_cameras.py --max-index 5
    python tools/list_cameras.py --snapshots     # save one JPEG per camera to data/camera_probe/
    python tools/list_cameras.py --preview 1     # live preview of index 1 (press q to close)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import cv2
except ImportError:  # keep the failure actionable
    sys.exit("OpenCV missing. Run: pip install -r requirements-tools.txt (inside the venv)")

BACKENDS = {"DSHOW": cv2.CAP_DSHOW, "MSMF": cv2.CAP_MSMF}


def probe(index: int, backend: int) -> dict | None:
    cap = cv2.VideoCapture(index, backend)
    try:
        if not cap.isOpened():
            return None
        frame = None
        for _ in range(10):  # webcams often return blank frames while auto-exposure settles
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
            time.sleep(0.05)
        if frame is None:
            return {"index": index, "opened": True, "frames": False}
        h, w = frame.shape[:2]
        return {
            "index": index,
            "opened": True,
            "frames": True,
            "width": w,
            "height": h,
            "fps_reported": cap.get(cv2.CAP_PROP_FPS),
            "mean_brightness": round(float(frame.mean()), 1),
            "frame": frame,
        }
    finally:
        cap.release()


def preview(index: int, backend: int) -> None:
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        sys.exit(f"Could not open camera {index}")
    title = f"camera index {index} - press q to close"
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.1)
            continue
        cv2.putText(frame, f"index {index}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow(title, frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-index", type=int, default=9)
    ap.add_argument("--backend", choices=BACKENDS, default="DSHOW")
    ap.add_argument("--snapshots", action="store_true", help="save one JPEG per working camera")
    ap.add_argument("--preview", type=int, metavar="INDEX")
    args = ap.parse_args()
    backend = BACKENDS[args.backend]

    if args.preview is not None:
        preview(args.preview, backend)
        return 0

    out_dir = Path("data/camera_probe")
    if args.snapshots:
        out_dir.mkdir(parents=True, exist_ok=True)

    found = 0
    for i in range(args.max_index + 1):
        info = probe(i, backend)
        if info is None:
            continue
        found += 1
        if not info["frames"]:
            print(f"[{i}] opened but no frames (in use by another app, or privacy shutter?)")
            continue
        print(f"[{i}] {info['width']}x{info['height']}  fps(reported)={info['fps_reported']:.0f}  "
              f"brightness={info['mean_brightness']}")
        if args.snapshots:
            path = out_dir / f"camera_{i}.jpg"
            cv2.imwrite(str(path), info["frame"])
            print(f"     saved {path}")
    print(f"\n{found} camera index(es) opened with {args.backend}.")
    if found == 0:
        print("No cameras found. Check USB connection, Windows Settings > Privacy > Camera "
              "(allow desktop apps), and that no other app is using the camera.")
    elif found == 1:
        print("Only one camera visible - the laptop's built-in camera may be the only one. "
              "Plug in the USB webcams and re-run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
