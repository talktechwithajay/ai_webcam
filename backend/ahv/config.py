"""Configuration loading.

Everything the owner must fill in (recorder, Home Assistant, dashboard login) lives in
one git-ignored file: config/settings.local.yaml (copy of config/settings.example.yaml).
Settings that are changed from the dashboard (retention, mutes, quiet hours) live in the
database instead, see db.Store settings.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "settings.local.yaml"
PLACEHOLDER_PASSWORDS = {"", "change-me", "changeme", "password"}
DEFAULT_RTSP_TEMPLATE = (
    "rtsp://{username}:{password}@{host}:{port}/cam/realmonitor?channel={channel}&subtype={subtype}"
)


class ConfigError(ValueError):
    pass


@dataclass
class DashboardCfg:
    host: str = "127.0.0.1"
    port: int = 8080
    username: str = "admin"
    password: str = ""
    session_hours: int = 12


@dataclass
class HomeAssistantCfg:
    enabled: bool = False
    base_url: str = "http://homeassistant.local:8123"
    webhook_id: str = ""
    timeout_seconds: int = 10


@dataclass
class RecorderCfg:
    host: str = ""
    rtsp_port: int = 554
    username: str = ""
    password: str = ""
    rtsp_url_template: str = DEFAULT_RTSP_TEMPLATE

    def url(self, channel: int, subtype: int) -> str:
        if not self.host:
            raise ConfigError("recorder.host is not set")
        return self.rtsp_url_template.format(
            username=quote(self.username, safe=""),
            password=quote(self.password, safe=""),
            host=self.host,
            port=self.rtsp_port,
            channel=channel,
            subtype=subtype,
        )


@dataclass
class CameraCfg:
    id: str
    role: str  # "front" | "indoor"
    label: str = ""
    source: str = "disabled"  # recorder | rtsp | usb | file | disabled
    channel: int = 1
    detect_subtype: int = 1
    snapshot_subtype: int = 0
    rtsp_url: str = ""
    usb_index: int = 0
    path: str = ""
    zone: list[float] | None = None  # [x1, y1, x2, y2] as fractions of the frame
    log_cooldown_seconds: int = 60
    announce_cooldown_seconds: int = 60

    @property
    def enabled(self) -> bool:
        return self.source != "disabled"


@dataclass
class RecognitionCfg:
    detect_score: float = 0.85
    match_threshold: float = 0.40  # SFace cosine; OpenCV suggests 0.363, higher = stricter
    process_fps: float = 5.0
    min_face_px: int = 70
    min_frames: int = 3
    settle_seconds: float = 1.5
    lost_seconds: float = 1.5
    max_templates_per_person: int = 8


@dataclass
class Config:
    dashboard: DashboardCfg = field(default_factory=DashboardCfg)
    home_assistant: HomeAssistantCfg = field(default_factory=HomeAssistantCfg)
    recorder: RecorderCfg = field(default_factory=RecorderCfg)
    cameras: list[CameraCfg] = field(default_factory=list)
    recognition: RecognitionCfg = field(default_factory=RecognitionCfg)
    data_dir: Path = REPO_ROOT / "data"
    models_dir: Path = REPO_ROOT / "models"
    frontend_dir: Path = REPO_ROOT / "frontend" / "dist"
    source_path: Path | None = None

    def camera(self, cam_id: str) -> CameraCfg | None:
        return next((c for c in self.cameras if c.id == cam_id), None)

    def camera_url(self, cam: CameraCfg, subtype: int | None = None) -> str:
        """Full stream URL (contains credentials: never log; use mask_url)."""
        if cam.source == "recorder":
            return self.recorder.url(cam.channel, cam.detect_subtype if subtype is None else subtype)
        if cam.source == "rtsp":
            if not cam.rtsp_url:
                raise ConfigError(f"camera {cam.id}: rtsp_url is empty")
            return cam.rtsp_url
        raise ConfigError(f"camera {cam.id}: source {cam.source!r} has no URL")


def mask_url(url: str) -> str:
    return re.sub(r"(://)[^/@]*@", r"\1***:***@", url)


def _pick(cls, data: dict | None, where: str):
    data = data or {}
    unknown = set(data) - set(cls.__dataclass_fields__)
    if unknown:
        raise ConfigError(f"{where}: unknown keys {sorted(unknown)}")
    return cls(**data)


def _resolve(path_str: str, base: Path) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (base / p)


def parse_config(raw: dict | None, source: Path | None = None) -> Config:
    raw = raw or {}
    cfg = Config(
        dashboard=_pick(DashboardCfg, raw.get("dashboard"), "dashboard"),
        home_assistant=_pick(HomeAssistantCfg, raw.get("home_assistant"), "home_assistant"),
        recorder=_pick(RecorderCfg, raw.get("recorder"), "recorder"),
        recognition=_pick(RecognitionCfg, raw.get("recognition"), "recognition"),
        source_path=source,
    )
    if "data_dir" in raw:
        cfg.data_dir = _resolve(raw["data_dir"], REPO_ROOT)
    if "models_dir" in raw:
        cfg.models_dir = _resolve(raw["models_dir"], REPO_ROOT)
    for cam_id, c in (raw.get("cameras") or {}).items():
        c = dict(c or {})
        c.setdefault("label", cam_id.replace("_", " ").title())
        cfg.cameras.append(_pick(CameraCfg, {"id": cam_id, **c}, f"cameras.{cam_id}"))
    for cam in cfg.cameras:
        if cam.role not in ("front", "indoor"):
            raise ConfigError(f"cameras.{cam.id}.role must be 'front' or 'indoor'")
        if cam.source not in ("recorder", "rtsp", "usb", "file", "disabled"):
            raise ConfigError(f"cameras.{cam.id}.source invalid: {cam.source!r}")
        if cam.zone is not None and (len(cam.zone) != 4 or not all(0 <= v <= 1 for v in cam.zone)):
            raise ConfigError(f"cameras.{cam.id}.zone must be [x1,y1,x2,y2] fractions 0..1")
        if cam.source == "file" and cam.path:
            cam.path = str(_resolve(cam.path, REPO_ROOT))
    return cfg


def load_config(path: str | os.PathLike | None = None) -> Config:
    path = Path(path or os.environ.get("AHV_CONFIG") or DEFAULT_CONFIG)
    if not path.exists():
        return parse_config({}, None)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {e}") from e
    return parse_config(raw, path)


def validate_for_run(cfg: Config) -> list[str]:
    """Return a list of blocking problems (empty = OK to start)."""
    problems = []
    if cfg.dashboard.password.strip().lower() in PLACEHOLDER_PASSWORDS and not os.environ.get(
        "AHV_ALLOW_DEFAULT_PASSWORD"
    ):
        problems.append("dashboard.password must be set to a real password in config/settings.local.yaml")
    if cfg.home_assistant.enabled and not cfg.home_assistant.webhook_id:
        problems.append("home_assistant.enabled is true but webhook_id is empty")
    for cam in cfg.cameras:
        if cam.source == "recorder" and not cfg.recorder.host:
            problems.append(f"camera {cam.id} uses the recorder but recorder.host is empty")
        if cam.source == "file" and not Path(cam.path).exists():
            problems.append(f"camera {cam.id}: file not found: {cam.path}")
    return problems
