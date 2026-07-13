"""Shimpz reviews — stars + comments from Captains who actually run the Shimpz.

SQLite on the store's own volume (the accounts service's proven pattern: stdlib, WAL, one file).
One review per (app, account), upsert = editing your review. The HONESTY GATE lives in the route,
not here: main.py only calls upsert() after confirming with the capsule-driver that the account has
this Shimpz installed in a Capsule it owns — the marketplace never shows a rating from someone who
never ran the thing.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("SHIMPZ_STORE_DB", "/data/store.db"))
APP_ID_RE = re.compile(
    r"^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$"
)  # same grammar the install path enforces
MAX_COMMENT = 1000
LIST_LIMIT = 100


class ReviewError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(
        "CREATE TABLE IF NOT EXISTS review("
        "app_id TEXT NOT NULL, account_id TEXT NOT NULL, username TEXT NOT NULL, "
        "stars INTEGER NOT NULL, comment TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL, "
        "PRIMARY KEY (app_id, account_id))"
    )
    return c


def validate_app_id(app_id: object) -> str:
    if not isinstance(app_id, str) or not APP_ID_RE.match(app_id):
        raise ReviewError(400, "bad app id")
    return app_id


def validate_stars(stars: object) -> int:
    # bool is an int subclass — refuse it explicitly, then require a whole 1..5
    if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= 5:
        raise ReviewError(400, "stars must be a whole number from 1 to 5")
    return stars


def validate_comment(comment: object) -> str:
    text = str(comment or "").strip()
    if len(text) > MAX_COMMENT:
        raise ReviewError(400, f"comment too long (> {MAX_COMMENT} chars)")
    return text


def upsert(
    app_id: str, account_id: str, username: str, stars: object, comment: object = ""
) -> dict:
    """Create or replace this account's review of this Shimpz. Inputs are validated here — the route
    only supplies identity (account_id/username come from the verified token, never the body)."""
    aid = validate_app_id(app_id)
    s = validate_stars(stars)
    text = validate_comment(comment)
    with _conn() as c:
        c.execute(
            "INSERT INTO review(app_id, account_id, username, stars, comment, updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(app_id, account_id) DO UPDATE SET username=excluded.username, stars=excluded.stars, "
            "comment=excluded.comment, updated_at=excluded.updated_at",
            (aid, account_id, username, s, text, int(time.time())),
        )
    return {"app": aid, "stars": s, "comment": text}


def for_app(app_id: str) -> dict:
    """Public aggregate + the latest reviews: {average, count, reviews:[{username, stars, comment, ts}]}."""
    aid = validate_app_id(app_id)
    with _conn() as c:
        agg = c.execute(
            "SELECT AVG(stars), COUNT(*) FROM review WHERE app_id=?", (aid,)
        ).fetchone()
        rows = c.execute(
            "SELECT username, stars, comment, updated_at FROM review WHERE app_id=? ORDER BY updated_at DESC LIMIT ?",
            (aid, LIST_LIMIT),
        ).fetchall()
    average, count = (round(agg[0], 2) if agg[0] is not None else None), agg[1]
    return {
        "app": aid,
        "average": average,
        "count": count,
        "reviews": [
            {"username": r[0], "stars": r[1], "comment": r[2], "ts": r[3]} for r in rows
        ],
    }
