"""SQLite storage: people, face templates, visits, indoor messages, settings.

Design notes
- A *person* is either enrolled (has a name) or unknown (status 'unknown', shown as
  "UNKNOWN #n"). Visits reference a person by id, so naming an unknown person renames
  every past (and future) visit at once: there is no per-visit name to update.
- Pictures and embeddings are encrypted (crypto.Vault). Embeddings are never returned
  through the API.
- Timestamps are stored as UTC ISO-8601 with millisecond precision (sortable as text).
"""
from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np

from .crypto import Vault

NAME_RE = re.compile(r"^[\w .'\-]{1,40}$", re.UNICODE)
MESSAGE_RE = re.compile(r"^[\w .,!?:'\-]{1,200}$", re.UNICODE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  status TEXT NOT NULL CHECK (status IN ('enrolled','unknown')),
  unknown_no INTEGER,
  muted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  embedding BLOB NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  camera TEXT NOT NULL,
  ts TEXT NOT NULL,
  confidence REAL,
  announced TEXT NOT NULL DEFAULT 'none',
  message TEXT,
  image_path TEXT,
  thumb_path TEXT,
  embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_visits_ts ON visits(ts);
CREATE INDEX IF NOT EXISTS idx_visits_person ON visits(person_id, ts);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  start_date TEXT,
  end_date TEXT,
  weekdays TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

SETTING_DEFAULTS = {
    "retention_days": "90",  # integer days, or "never"
    "global_mute": "false",
    "quiet_hours_enabled": "true",
    "quiet_start": "22:00",
    "quiet_end": "07:00",
    "announce_unknown_front": "true",
    "indoor_log_unknown": "false",
    "welcome_enabled": "true",
    "dry_run": "true",  # safe default: log what would be said, send nothing
}


class ValidationError(ValueError):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def local_day_bounds(d: date) -> tuple[str, str]:
    """[start, end) of a local calendar day as UTC ISO strings."""
    start = datetime.combine(d, time.min).astimezone()
    end = datetime.combine(d + timedelta(days=1), time.min).astimezone()
    return iso(start), iso(end)


def validate_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_RE.match(name) or name.upper().startswith("UNKNOWN"):
        raise ValidationError("Name must be 1-40 characters: letters, digits, space . ' - (and not start with UNKNOWN)")
    return name


def validate_message(text: str) -> str:
    text = " ".join((text or "").split())
    if not MESSAGE_RE.match(text):
        raise ValidationError("Message must be 1-200 characters: letters, digits, spaces and . , ! ? : ' -")
    return text


def person_label(row) -> str:
    return row["name"] if row["status"] == "enrolled" else f"UNKNOWN #{row['unknown_no']}"


class Store:
    def __init__(self, data_dir: Path, vault: Vault, db_name: str = "ahv.db"):
        self.data_dir = Path(data_dir)
        self.image_dir = self.data_dir / "images"
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.vault = vault
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.data_dir / db_name, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self.templates_version = 0

    @property
    def lock(self) -> threading.RLock:
        """Hold this around create_person()+add_visit() so a purge cannot drop the empty person in between."""
        return self._lock

    @contextmanager
    def tx(self):
        with self._lock:
            try:
                yield self._db
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise

    def q(self, sql: str, args=()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    def q1(self, sql: str, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    # ---------------------------------------------------------------- settings
    def get_settings(self) -> dict:
        vals = {r["key"]: r["value"] for r in self.q("SELECT key, value FROM settings")}
        merged = {**SETTING_DEFAULTS, **vals}
        return {
            "retention_days": merged["retention_days"] if merged["retention_days"] == "never" else int(merged["retention_days"]),
            "global_mute": merged["global_mute"] == "true",
            "quiet_hours_enabled": merged["quiet_hours_enabled"] == "true",
            "quiet_start": merged["quiet_start"],
            "quiet_end": merged["quiet_end"],
            "announce_unknown_front": merged["announce_unknown_front"] == "true",
            "indoor_log_unknown": merged["indoor_log_unknown"] == "true",
            "welcome_enabled": merged["welcome_enabled"] == "true",
            "dry_run": merged["dry_run"] == "true",
        }

    def update_settings(self, changes: dict) -> dict:
        clean: dict[str, str] = {}
        for k, v in changes.items():
            if k not in SETTING_DEFAULTS:
                raise ValidationError(f"unknown setting {k!r}")
            if k == "retention_days":
                if v == "never":
                    clean[k] = "never"
                else:
                    try:
                        days = int(v)
                    except (TypeError, ValueError):
                        raise ValidationError("retention_days must be a whole number of days or 'never'")
                    if not 1 <= days <= 3650:
                        raise ValidationError("retention_days must be between 1 and 3650, or 'never'")
                    clean[k] = str(days)
            elif k in ("quiet_start", "quiet_end"):
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(v)):
                    raise ValidationError(f"{k} must be HH:MM")
                clean[k] = str(v)
            else:
                if not isinstance(v, bool):
                    raise ValidationError(f"{k} must be true or false")
                clean[k] = "true" if v else "false"
        with self.tx() as db:
            for k, v in clean.items():
                db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        return self.get_settings()

    # ----------------------------------------------------------------- people
    def create_person(self, name: str | None = None, muted: bool = False) -> int:
        with self.tx() as db:
            if name is not None:
                name = validate_name(name)
                if db.execute("SELECT 1 FROM persons WHERE status='enrolled' AND lower(name)=lower(?)", (name,)).fetchone():
                    raise ValidationError(f"A person named {name!r} already exists. Use merge instead.")
                cur = db.execute(
                    "INSERT INTO persons(name,status,muted,created_at) VALUES(?, 'enrolled', ?, ?)",
                    (name, int(muted), iso(now_utc())),
                )
            else:
                n = db.execute("SELECT COALESCE(MAX(unknown_no),0)+1 FROM persons WHERE status='unknown'").fetchone()[0]
                cur = db.execute(
                    "INSERT INTO persons(status,unknown_no,created_at) VALUES('unknown', ?, ?)", (n, iso(now_utc()))
                )
            return cur.lastrowid

    def get_person(self, person_id: int):
        return self.q1("SELECT * FROM persons WHERE id=?", (person_id,))

    def list_people(self, status: str | None = None, search: str | None = None) -> list[dict]:
        sql = """
        SELECT p.*, COUNT(v.id) AS visit_count, MIN(v.ts) AS first_seen, MAX(v.ts) AS last_seen,
               (SELECT id FROM visits WHERE person_id=p.id ORDER BY ts DESC LIMIT 1) AS thumb_visit_id,
               (SELECT COUNT(*) FROM messages m WHERE m.person_id=p.id AND m.enabled=1) AS message_count
        FROM persons p LEFT JOIN visits v ON v.person_id=p.id
        WHERE 1=1"""
        args: list = []
        if status:
            sql += " AND p.status=?"
            args.append(status)
        sql += " GROUP BY p.id ORDER BY (MAX(v.ts) IS NULL), MAX(v.ts) DESC, p.id DESC"
        out = []
        for r in self.q(sql, args):
            d = self._person_dict(r)
            if search and search.lower() not in d["label"].lower():
                continue
            out.append(d)
        return out

    @staticmethod
    def _person_dict(r) -> dict:
        return {
            "id": r["id"],
            "name": r["name"],
            "label": person_label(r),
            "status": r["status"],
            "muted": bool(r["muted"]),
            "visit_count": r["visit_count"],
            "first_seen": r["first_seen"],
            "last_seen": r["last_seen"],
            "thumb_visit_id": r["thumb_visit_id"],
            "message_count": r["message_count"],
        }

    def person_detail(self, person_id: int) -> dict | None:
        for d in self.list_people():
            if d["id"] == person_id:
                return d
        return None

    def name_person(self, person_id: int, name: str) -> dict:
        """Name (enrol) an unknown person, or rename an enrolled one. All visits follow."""
        name = validate_name(name)
        with self.tx() as db:
            row = db.execute("SELECT * FROM persons WHERE id=?", (person_id,)).fetchone()
            if not row:
                raise KeyError("person not found")
            clash = db.execute(
                "SELECT id FROM persons WHERE status='enrolled' AND lower(name)=lower(?) AND id<>?", (name, person_id)
            ).fetchone()
            if clash:
                raise ValidationError(
                    f"{name!r} already exists (person #{clash['id']}). Merge this person into them instead."
                )
            db.execute("UPDATE persons SET name=?, status='enrolled', unknown_no=NULL WHERE id=?", (name, person_id))
        self.templates_version += 1
        return self.person_detail(person_id)

    def set_muted(self, person_id: int, muted: bool) -> None:
        with self.tx() as db:
            if db.execute("UPDATE persons SET muted=? WHERE id=?", (int(muted), person_id)).rowcount == 0:
                raise KeyError("person not found")

    def set_all_muted(self, muted: bool) -> None:
        with self.tx() as db:
            db.execute("UPDATE persons SET muted=?", (int(muted),))

    def merge_people(self, source_id: int, target_id: int) -> dict:
        if source_id == target_id:
            raise ValidationError("Cannot merge a person into themselves")
        with self.tx() as db:
            src = db.execute("SELECT * FROM persons WHERE id=?", (source_id,)).fetchone()
            dst = db.execute("SELECT * FROM persons WHERE id=?", (target_id,)).fetchone()
            if not src or not dst:
                raise KeyError("person not found")
            if src["status"] == "enrolled" and dst["status"] == "unknown":
                raise ValidationError("Merge the unknown person into the named one, not the other way round")
            for table in ("templates", "visits", "messages"):
                db.execute(f"UPDATE {table} SET person_id=? WHERE person_id=?", (target_id, source_id))
            if src["muted"] and not dst["muted"]:
                db.execute("UPDATE persons SET muted=1 WHERE id=?", (target_id,))
            db.execute("DELETE FROM persons WHERE id=?", (source_id,))
        self.templates_version += 1
        return self.person_detail(target_id)

    def delete_person(self, person_id: int) -> int:
        """Delete a person with all their visits, pictures, templates and messages."""
        with self.tx() as db:
            paths = db.execute(
                "SELECT image_path, thumb_path FROM visits WHERE person_id=?", (person_id,)
            ).fetchall()
            n = db.execute("DELETE FROM persons WHERE id=?", (person_id,)).rowcount
        for p in paths:
            self._unlink(p["image_path"], p["thumb_path"])
        self.templates_version += 1
        if not n:
            raise KeyError("person not found")
        return len(paths)

    # -------------------------------------------------------------- templates
    def add_template(self, person_id: int, embedding: np.ndarray, max_templates: int = 8) -> bool:
        """Store an embedding unless it is near-identical to an existing one. Returns True if stored."""
        emb = _norm(embedding)
        with self.tx() as db:
            rows = db.execute("SELECT id, embedding FROM templates WHERE person_id=? ORDER BY id", (person_id,)).fetchall()
            vecs = [self._load_emb(r["embedding"]) for r in rows]
            if any(float(emb @ v) > 0.92 for v in vecs):
                return False
            if len(rows) >= max_templates:
                db.execute("DELETE FROM templates WHERE id=?", (rows[0]["id"],))  # drop the oldest
            db.execute(
                "INSERT INTO templates(person_id, embedding, created_at) VALUES(?,?,?)",
                (person_id, self._dump_emb(emb), iso(now_utc())),
            )
        self.templates_version += 1
        return True

    def load_templates(self) -> list[tuple[int, str, np.ndarray]]:
        rows = self.q(
            "SELECT t.person_id, p.status, t.embedding FROM templates t JOIN persons p ON p.id=t.person_id"
        )
        return [(r["person_id"], r["status"], self._load_emb(r["embedding"])) for r in rows]

    def _dump_emb(self, emb: np.ndarray) -> bytes:
        return self.vault.encrypt(np.asarray(emb, dtype=np.float32).tobytes())

    def _load_emb(self, blob: bytes) -> np.ndarray:
        return np.frombuffer(self.vault.decrypt(blob), dtype=np.float32)

    # ----------------------------------------------------------------- visits
    def add_visit(self, person_id: int, camera: str, ts: datetime, confidence: float | None,
                  image_jpeg: bytes, thumb_jpeg: bytes, embedding: np.ndarray | None) -> int:
        stamp = ts.astimezone()
        rel_dir = Path(f"{stamp:%Y}") / f"{stamp:%m}" / f"{stamp:%d}"
        (self.image_dir / rel_dir).mkdir(parents=True, exist_ok=True)
        base = uuid.uuid4().hex
        img_rel, thumb_rel = str(rel_dir / f"{base}.jpg.enc"), str(rel_dir / f"{base}_t.jpg.enc")
        (self.image_dir / img_rel).write_bytes(self.vault.encrypt(image_jpeg))
        (self.image_dir / thumb_rel).write_bytes(self.vault.encrypt(thumb_jpeg))
        try:
            with self.tx() as db:
                cur = db.execute(
                    "INSERT INTO visits(person_id,camera,ts,confidence,announced,image_path,thumb_path,embedding)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (person_id, camera, iso(ts), confidence, "pending", img_rel, thumb_rel,
                     self._dump_emb(embedding) if embedding is not None else None),
                )
                return cur.lastrowid
        except Exception:
            self._unlink(img_rel, thumb_rel)
            raise

    def update_visit_announce(self, visit_id: int, status: str, message: str | None) -> None:
        with self.tx() as db:
            db.execute("UPDATE visits SET announced=?, message=? WHERE id=?", (status, message, visit_id))

    def last_visit_time(self, person_id: int, camera: str, announced_only: bool = False) -> datetime | None:
        sql = "SELECT MAX(ts) AS t FROM visits WHERE person_id=? AND camera=?"
        if announced_only:
            sql += " AND announced IN ('sent','dry_run')"
        row = self.q1(sql, (person_id, camera))
        return datetime.fromisoformat(row["t"]) if row and row["t"] else None

    def query_visits(self, date_from: date | None = None, date_to: date | None = None, camera: str | None = None,
                     person_id: int | None = None, kind: str = "all", limit: int = 50, offset: int = 0,
                     order: str = "desc") -> dict:
        where, args = ["1=1"], []
        if date_from:
            where.append("v.ts >= ?")
            args.append(local_day_bounds(date_from)[0])
        if date_to:
            where.append("v.ts < ?")
            args.append(local_day_bounds(date_to)[1])
        if camera:
            where.append("v.camera=?")
            args.append(camera)
        if person_id:
            where.append("v.person_id=?")
            args.append(person_id)
        if kind == "known":
            where.append("p.status='enrolled'")
        elif kind == "unknown":
            where.append("p.status='unknown'")
        elif kind != "all":
            raise ValidationError("kind must be all, known or unknown")
        w = " AND ".join(where)
        total = self.q1(f"SELECT COUNT(*) AS n FROM visits v JOIN persons p ON p.id=v.person_id WHERE {w}", args)["n"]
        direction = "ASC" if order == "asc" else "DESC"
        rows = self.q(
            f"""SELECT v.id, v.person_id, v.camera, v.ts, v.confidence, v.announced, v.message,
                       p.name, p.status, p.unknown_no
                FROM visits v JOIN persons p ON p.id=v.person_id WHERE {w}
                ORDER BY v.ts {direction}, v.id {direction} LIMIT ? OFFSET ?""",
            [*args, max(1, min(limit, 500)), max(0, offset)],
        )
        items = [
            {
                "id": r["id"], "person_id": r["person_id"], "camera": r["camera"], "ts": r["ts"],
                "confidence": r["confidence"], "announced": r["announced"], "message": r["message"],
                "label": person_label(r), "status": r["status"],
            }
            for r in rows
        ]
        return {"total": total, "items": items}

    def visit_image(self, visit_id: int, thumb: bool = False) -> bytes | None:
        row = self.q1("SELECT image_path, thumb_path FROM visits WHERE id=?", (visit_id,))
        if not row:
            return None
        rel = row["thumb_path"] if thumb else row["image_path"]
        path = self.image_dir / rel if rel else None
        if not path or not path.exists():
            return None
        return self.vault.decrypt(path.read_bytes())

    def delete_visits(self, visit_ids: list[int]) -> int:
        if not visit_ids:
            return 0
        marks = ",".join("?" * len(visit_ids))
        with self.tx() as db:
            paths = db.execute(f"SELECT image_path, thumb_path FROM visits WHERE id IN ({marks})", visit_ids).fetchall()
            db.execute(f"DELETE FROM visits WHERE id IN ({marks})", visit_ids)
        for p in paths:
            self._unlink(p["image_path"], p["thumb_path"])
        self._drop_empty_unknowns()
        return len(paths)

    def delete_visits_in_range(self, date_from: date | None, date_to: date | None, person_id: int | None = None) -> int:
        where, args = ["1=1"], []
        if date_from:
            where.append("ts >= ?")
            args.append(local_day_bounds(date_from)[0])
        if date_to:
            where.append("ts < ?")
            args.append(local_day_bounds(date_to)[1])
        if person_id:
            where.append("person_id=?")
            args.append(person_id)
        if len(where) == 1:
            raise ValidationError("Refusing to delete all visits without a date range or person")
        ids = [r["id"] for r in self.q(f"SELECT id FROM visits WHERE {' AND '.join(where)}", args)]
        return self.delete_visits(ids)

    def assign_visit(self, visit_id: int, person_id: int | None, max_templates: int = 8) -> dict:
        """Move one visit to another person, or to a brand-new unknown person (person_id=None)."""
        row = self.q1("SELECT * FROM visits WHERE id=?", (visit_id,))
        if not row:
            raise KeyError("visit not found")
        if person_id is None:
            person_id = self.create_person(None)
        elif not self.get_person(person_id):
            raise KeyError("person not found")
        with self.tx() as db:
            db.execute("UPDATE visits SET person_id=? WHERE id=?", (person_id, visit_id))
        if row["embedding"]:
            self.add_template(person_id, self._load_emb(row["embedding"]), max_templates)
        self._drop_empty_unknowns()
        self.templates_version += 1
        return self.person_detail(person_id)

    # ----------------------------------------------------------------- messages
    def list_messages(self, person_id: int | None = None) -> list[dict]:
        sql = "SELECT m.*, p.name FROM messages m JOIN persons p ON p.id=m.person_id"
        args: list = []
        if person_id:
            sql += " WHERE m.person_id=?"
            args.append(person_id)
        return [self._message_dict(r) for r in self.q(sql + " ORDER BY m.id DESC", args)]

    @staticmethod
    def _message_dict(r) -> dict:
        return {
            "id": r["id"], "person_id": r["person_id"], "person_name": r["name"], "text": r["text"],
            "start_date": r["start_date"], "end_date": r["end_date"],
            "weekdays": [int(x) for x in r["weekdays"].split(",")] if r["weekdays"] else [],
            "enabled": bool(r["enabled"]),
        }

    def save_message(self, person_id: int, text: str, start_date: str | None = None, end_date: str | None = None,
                     weekdays: list[int] | None = None, enabled: bool = True, message_id: int | None = None) -> int:
        text = validate_message(text)
        p = self.get_person(person_id)
        if not p or p["status"] != "enrolled":
            raise ValidationError("Messages can only be set for named people")
        for d in (start_date, end_date):
            if d:
                try:
                    date.fromisoformat(d)
                except ValueError:
                    raise ValidationError("Dates must be YYYY-MM-DD")
        if start_date and end_date and start_date > end_date:
            raise ValidationError("start_date is after end_date")
        wd = sorted(set(weekdays or []))
        if any(not isinstance(x, int) or not 0 <= x <= 6 for x in wd):
            raise ValidationError("weekdays are 0 (Monday) to 6 (Sunday)")
        wd_s = ",".join(map(str, wd)) or None
        with self.tx() as db:
            if message_id:
                if not db.execute(
                    "UPDATE messages SET person_id=?, text=?, start_date=?, end_date=?, weekdays=?, enabled=? WHERE id=?",
                    (person_id, text, start_date or None, end_date or None, wd_s, int(enabled), message_id),
                ).rowcount:
                    raise KeyError("message not found")
                return message_id
            return db.execute(
                "INSERT INTO messages(person_id,text,start_date,end_date,weekdays,enabled,created_at) VALUES(?,?,?,?,?,?,?)",
                (person_id, text, start_date or None, end_date or None, wd_s, int(enabled), iso(now_utc())),
            ).lastrowid

    def delete_message(self, message_id: int) -> None:
        with self.tx() as db:
            if not db.execute("DELETE FROM messages WHERE id=?", (message_id,)).rowcount:
                raise KeyError("message not found")

    def active_message(self, person_id: int, today: date) -> str | None:
        """Newest enabled message whose date range and weekday rule match today."""
        for m in self.list_messages(person_id):
            if not m["enabled"]:
                continue
            if m["start_date"] and today.isoformat() < m["start_date"]:
                continue
            if m["end_date"] and today.isoformat() > m["end_date"]:
                continue
            if m["weekdays"] and today.weekday() not in m["weekdays"]:
                continue
            return m["text"]
        return None

    # ---------------------------------------------------------------- retention
    def retention_candidates(self, days: int, now: datetime | None = None) -> list[int]:
        cutoff = iso((now or now_utc()) - timedelta(days=days))
        rows = self.q(
            "SELECT v.id FROM visits v JOIN persons p ON p.id=v.person_id WHERE p.status='unknown' AND v.ts < ?",
            (cutoff,),
        )
        return [r["id"] for r in rows]

    def purge_unknown_older_than(self, days: int, now: datetime | None = None) -> int:
        return self.delete_visits(self.retention_candidates(days, now))

    def _drop_empty_unknowns(self) -> None:
        with self.tx() as db:
            db.execute(
                "DELETE FROM persons WHERE status='unknown' AND NOT EXISTS (SELECT 1 FROM visits v WHERE v.person_id=persons.id)"
            )
        self.templates_version += 1

    def _unlink(self, *rels: str | None) -> None:
        for rel in rels:
            if rel:
                try:
                    (self.image_dir / rel).unlink(missing_ok=True)
                except OSError:
                    pass

    def stats(self) -> dict:
        r = self.q1(
            "SELECT (SELECT COUNT(*) FROM visits) AS visits, (SELECT COUNT(*) FROM persons WHERE status='enrolled') AS known,"
            " (SELECT COUNT(*) FROM persons WHERE status='unknown') AS unknown"
        )
        return dict(r)

    def close(self) -> None:
        with self._lock:
            self._db.close()


def _norm(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return v / n if n else v
