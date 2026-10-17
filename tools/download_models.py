"""Download the two face models into models/ and verify their SHA-256.

  YuNet (face detection)   MIT licence           github.com/opencv/opencv_zoo
  SFace (face embedding)   Apache-2.0 (zoo code)  github.com/opencv/opencv_zoo

Check the upstream model cards yourself before relying on them for anything beyond
personal home use: the training-data terms of face-recognition models can differ from
the licence on the weights file.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    out = ROOT / "models"
    out.mkdir(exist_ok=True)
    rc = 0
    for name, (url, digest) in MODELS.items():
        dest = out / name
        if dest.exists() and sha256(dest) == digest:
            print(f"ok      {name} (already present)")
            continue
        print(f"fetch   {name} ...")
        tmp = dest.with_suffix(".part")
        try:
            urllib.request.urlretrieve(url, tmp)
        except OSError as e:
            print(f"FAILED  {name}: {e}")
            rc = 1
            continue
        if sha256(tmp) != digest:
            tmp.unlink(missing_ok=True)
            print(f"FAILED  {name}: checksum mismatch (upstream file changed or download corrupted)")
            rc = 1
            continue
        tmp.replace(dest)
        print(f"ok      {name}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
