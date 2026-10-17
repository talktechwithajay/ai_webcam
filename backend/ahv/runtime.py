"""Wiring: build the whole system from a Config, run retention, serve the dashboard."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from .announce import Announcer
from .api import Auth, create_app
from .config import Config
from .crypto import Vault
from .db import Store
from .faces import FaceEngine, OpenCVFaceEngine
from .pipeline import Supervisor

log = logging.getLogger("ahv.runtime")


@dataclass
class System:
    cfg: Config
    vault: Vault
    store: Store
    announcer: Announcer
    engine: FaceEngine | None
    supervisor: Supervisor | None
    app: object


class RetentionJob(threading.Thread):
    """Hourly check; deletes UNKNOWN visits older than the Settings value (never = skip)."""

    def __init__(self, store: Store, interval_s: float = 3600):
        super().__init__(name="retention", daemon=True)
        self.store, self.interval = store, interval_s
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                days = self.store.get_settings()["retention_days"]
                if days != "never":
                    n = self.store.purge_unknown_older_than(days)
                    if n:
                        log.info("retention: deleted %s unknown-visitor visits older than %s days", n, days)
            except Exception:
                log.exception("retention job failed")
            self._halt.wait(self.interval)

    def stop(self) -> None:
        self._halt.set()


def build_system(cfg: Config, engine: FaceEngine | None = None, start_cameras: bool = True,
                 load_models: bool = True) -> System:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    vault = Vault(cfg.data_dir / "secret.key")
    store = Store(cfg.data_dir, vault)
    if engine is None and load_models:
        try:
            engine = OpenCVFaceEngine(cfg.models_dir, cfg.recognition.detect_score)
        except FileNotFoundError as e:
            log.warning("%s - recognition disabled until models are installed", e)
    announcer = Announcer(cfg.home_assistant, lambda: store.get_settings()["dry_run"])
    supervisor = None
    if engine is not None and start_cameras and any(c.enabled for c in cfg.cameras):
        supervisor = Supervisor(cfg, store, engine, announcer)
        supervisor.start()
    auth = Auth(cfg, vault)
    app = create_app(cfg, store, auth, announcer, engine, supervisor)
    return System(cfg, vault, store, announcer, engine, supervisor, app)
