"""SQLite persistence of numeric aggregates and coded events only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3

UTC = timezone.utc
_CODE = re.compile(r"^[a-z0-9_:-]{0,64}$")
SCHEMA = """
CREATE TABLE IF NOT EXISTS minute_stats (
  ts_minute TEXT PRIMARY KEY,
  present_ratio REAL NOT NULL,
  facing_screen REAL,
  input_activity REAL,
  app_switches INTEGER,
  focus_score REAL,
  label TEXT NOT NULL CHECK(label IN ('focused','neutral','distracted','away','unavailable'))
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS focus_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  start_ts TEXT NOT NULL,
  end_ts TEXT NOT NULL,
  avg_score REAL NOT NULL
);
"""


def iso_utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timezone-aware datetime required")
    return moment.astimezone(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path, retention_days: int = 90):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Construction happens before the worker starts; all subsequent writes
        # are serialized by that worker.
        self.connection = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA)
        self.retention_days = retention_days
        self.cleanup()

    def close(self):
        self.connection.close()

    def event(self, kind: str, detail: str | None = None, at: datetime | None = None):
        if not _CODE.fullmatch(kind) or (detail is not None and not _CODE.fullmatch(detail)):
            raise ValueError("event fields must be short non-identifying codes")
        at = at or datetime.now(UTC)
        with self.connection:
            self.connection.execute("INSERT INTO events(ts,type,detail) VALUES(?,?,?)", (iso_utc(at), kind, detail))

    def minute(self, at: datetime, *, present_ratio: float, facing_screen: float | None,
               input_activity: float | None, app_switches: int | None,
               focus_score: float | None, label: str):
        if label not in {"focused", "neutral", "distracted", "away", "unavailable"}:
            raise ValueError("invalid label")
        if not 0 <= present_ratio <= 1:
            raise ValueError("invalid present ratio")
        minute = at.astimezone(UTC).replace(second=0, microsecond=0)
        with self.connection:
            self.connection.execute("""INSERT INTO minute_stats VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(ts_minute) DO UPDATE SET
                present_ratio=excluded.present_ratio,facing_screen=excluded.facing_screen,
                input_activity=excluded.input_activity,app_switches=excluded.app_switches,
                focus_score=excluded.focus_score,label=excluded.label""",
                (iso_utc(minute), present_ratio, facing_screen, input_activity,
                 app_switches, focus_score, label))

    def session(self, start: datetime, end: datetime, avg_score: float):
        if end <= start or not 0 <= avg_score <= 100:
            raise ValueError("invalid focus session")
        with self.connection:
            self.connection.execute("INSERT INTO focus_sessions(start_ts,end_ts,avg_score) VALUES(?,?,?)",
                                    (iso_utc(start), iso_utc(end), avg_score))

    def cleanup(self, at: datetime | None = None):
        cutoff = iso_utc((at or datetime.now(UTC)) - timedelta(days=self.retention_days))
        with self.connection:
            self.connection.execute("DELETE FROM minute_stats WHERE ts_minute < ?", (cutoff,))
            self.connection.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self.connection.execute("DELETE FROM focus_sessions WHERE end_ts < ?", (cutoff,))


def read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection
