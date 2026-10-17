"""Command line:  python -m ahv <command>

  serve            start cameras + dashboard (default)
  check-config     validate config/settings.local.yaml and print what was understood
  check-cameras    open every configured camera, grab a frame, run face detection, save test snapshots
  seed-demo        fill the database with demo visitors (for trying the dashboard without cameras)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .config import ConfigError, load_config, mask_url, validate_for_run


def cmd_check_config(args) -> int:
    cfg = load_config(args.config)
    print(f"Config file : {cfg.source_path or 'NOT FOUND (using defaults) - copy config/settings.example.yaml'}")
    print(f"Dashboard   : http://{cfg.dashboard.host}:{cfg.dashboard.port}  user={cfg.dashboard.username}")
    print(f"Home Assist.: enabled={cfg.home_assistant.enabled} base_url={cfg.home_assistant.base_url}"
          f" webhook_id={'set' if cfg.home_assistant.webhook_id else 'EMPTY'}")
    print(f"Recorder    : host={cfg.recorder.host or 'EMPTY'} port={cfg.recorder.rtsp_port}"
          f" user={'set' if cfg.recorder.username else 'EMPTY'} password={'set' if cfg.recorder.password else 'EMPTY'}")
    for cam in cfg.cameras:
        where = ""
        if cam.source in ("recorder", "rtsp"):
            try:
                where = mask_url(cfg.camera_url(cam))
            except ConfigError as e:
                where = f"ERROR {e}"
        print(f"Camera {cam.id:<12} role={cam.role:<7} source={cam.source:<9} {where}")
    problems = validate_for_run(cfg)
    for p in problems:
        print("PROBLEM:", p)
    print("OK" if not problems else f"{len(problems)} problem(s) found")
    return 1 if problems else 0


def cmd_check_cameras(args) -> int:
    import cv2

    from .camera import open_capture
    from .faces import OpenCVFaceEngine

    cfg = load_config(args.config)
    out_dir = cfg.data_dir / "camera_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        engine = OpenCVFaceEngine(cfg.models_dir, cfg.recognition.detect_score)
    except FileNotFoundError as e:
        engine = None
        print(f"NOTE: {e} (face detection will be skipped)")
    rc = 0
    cams = [c for c in cfg.cameras if c.enabled]
    if not cams:
        print("No camera has a source configured. Edit config/settings.local.yaml.")
        return 1
    for cam in cams:
        subtypes = [cam.detect_subtype, cam.snapshot_subtype] if cam.source == "recorder" else [None]
        for st in dict.fromkeys(subtypes):
            tag = f"{cam.id}" + (f" subtype={st}" if st is not None else "")
            try:
                label = mask_url(cfg.camera_url(cam, st)) if cam.source in ("recorder", "rtsp") else cam.source
            except ConfigError as e:
                print(f"FAIL {tag}: {e}")
                rc = 1
                continue
            t0 = time.time()
            try:
                cap, static = open_capture(cfg, cam, st)
                frame = static
                if cap is not None:
                    if not cap.isOpened():
                        print(f"FAIL {tag}: cannot open {label}\n     check: recorder IP/port, RTSP enabled on the recorder,"
                              " user/password, channel number, or try another rtsp_url_template. Test the URL in VLC first.")
                        rc = 1
                        continue
                    for _ in range(5):
                        ok, f = cap.read()
                        if ok:
                            frame = f
                    cap.release()
                if frame is None:
                    print(f"FAIL {tag}: connected but no frame decoded (H.265 stream? set the recorder to H.264)")
                    rc = 1
                    continue
                h, w = frame.shape[:2]
                faces = engine.detect(frame) if engine else []
                for f in faces:
                    cv2.rectangle(frame, (f.x, f.y), (f.x + f.w, f.y + f.h), (0, 255, 0), 2)
                path = out_dir / f"{tag.replace(' ', '_').replace('=', '')}.jpg"
                cv2.imwrite(str(path), frame)
                print(f"OK   {tag}: {w}x{h} in {time.time() - t0:.1f}s, faces seen: {len(faces)}, snapshot: {path}")
            except Exception as e:
                print(f"FAIL {tag}: {mask_url(str(e))}")
                rc = 1
    print("Snapshots are personal data: delete data/camera_check/ when done.")
    return rc


def cmd_seed_demo(args) -> int:
    from .demo import seed_demo
    from .crypto import Vault
    from .db import Store

    cfg = load_config(args.config)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(cfg.data_dir, Vault(cfg.data_dir / "secret.key"))
    if store.stats()["visits"] and not args.force:
        print("Database already has visits; use --force to add demo data anyway.")
        return 1
    n = seed_demo(store)
    print(f"Added {n} demo visits. Delete them from the dashboard (or remove data/) when finished.")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .runtime import RetentionJob, build_system

    cfg = load_config(args.config)
    problems = validate_for_run(cfg)
    if problems:
        print("Cannot start:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 2
    system = build_system(cfg)
    RetentionJob(system.store).start()
    if not cfg.frontend_dir.exists():
        logging.warning("Frontend not built (%s missing). Run: cd frontend; npm install; npm run build", cfg.frontend_dir)
    logging.info("Dashboard: http://%s:%s", "localhost" if cfg.dashboard.host in ("0.0.0.0", "::") else cfg.dashboard.host,
                 cfg.dashboard.port)
    uvicorn.run(system.app, host=cfg.dashboard.host, port=cfg.dashboard.port, log_level="warning")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ahv", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="serve",
                    choices=["serve", "check-config", "check-cameras", "seed-demo"])
    ap.add_argument("--config", help="path to settings file (default config/settings.local.yaml)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        return {"serve": cmd_serve, "check-config": cmd_check_config,
                "check-cameras": cmd_check_cameras, "seed-demo": cmd_seed_demo}[args.command](args)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
