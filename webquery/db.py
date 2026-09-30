"""SQLite árelőzmény."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at    TEXT NOT NULL,            -- UTC, ISO 8601
    url           TEXT NOT NULL,
    name          TEXT,
    status        TEXT NOT NULL,            -- ok | blocked | error
    price         TEXT,                     -- Decimal szövegként, pl. '42.68'
    currency      TEXT,
    available     INTEGER,
    availability  TEXT,
    message       TEXT
);
CREATE INDEX IF NOT EXISTS checks_url_time ON checks (url, checked_at);

CREATE TABLE IF NOT EXISTS notifications (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at   TEXT NOT NULL,
    url       TEXT NOT NULL,
    price     TEXT NOT NULL,
    limit_    TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def record_check(conn, *, url, name, status, price=None, currency=None,
                 available=None, availability=None, message=None) -> None:
    conn.execute(
        "INSERT INTO checks (checked_at, url, name, status, price, currency, available,"
        " availability, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (now(), url, name, status, None if price is None else str(price), currency,
         None if available is None else int(available), availability, message),
    )
    conn.commit()


def previous_ok_check(conn, url):
    """Az utolsó előtti sikeres mérés (az aktuálist már beírtuk)."""
    rows = conn.execute(
        "SELECT * FROM checks WHERE url = ? AND status = 'ok' ORDER BY id DESC LIMIT 2",
        (url,),
    ).fetchall()
    return rows[1] if len(rows) > 1 else None


def last_notification(conn, url):
    return conn.execute(
        "SELECT * FROM notifications WHERE url = ? ORDER BY id DESC LIMIT 1", (url,)
    ).fetchone()


def record_notification(conn, url, price, limit) -> None:
    conn.execute(
        "INSERT INTO notifications (sent_at, url, price, limit_) VALUES (?, ?, ?, ?)",
        (now(), url, str(price), str(limit)),
    )
    conn.commit()


def history(conn, limit=20):
    return conn.execute(
        "SELECT checked_at, name, status, price, currency, available, message"
        " FROM checks ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
