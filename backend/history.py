"""Per-browser report history in SQLite. Owners are hashed random client tokens, not accounts."""
from contextlib import closing
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote

from fastapi import Request

# ponytail: SQLite on local disk; move to PostgreSQL when running more than one backend replica.
DB_PATH = os.getenv("DEEPGUARD_DB", str(Path(__file__).resolve().parent.parent / "data" / "reports.db"))
ENABLED = os.getenv("DEEPGUARD_HISTORY", "1") != "0"
MAX_PER_OWNER = int(os.getenv("DEEPGUARD_HISTORY_LIMIT", "50"))
TOKEN = re.compile(r"[A-Za-z0-9-]{16,128}")
logger = logging.getLogger("deepguard.history")


def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, created_at TEXT NOT NULL, media_type TEXT NOT NULL,
        filename TEXT, verdict TEXT NOT NULL, ai_score REAL, sha256 TEXT NOT NULL, body TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS reports_owner ON reports(owner, created_at)")
    return db


def owner(request: Request):
    token = request.headers.get("x-deepguard-client", "")
    return hashlib.sha256(token.encode()).hexdigest() if ENABLED and TOKEN.fullmatch(token) else None


def save(request: Request, report: dict):
    """Never fails the analysis: history is a convenience, the response is the source of truth."""
    key = owner(request)
    if key is None:
        return
    name = "".join(ch for ch in unquote(request.headers.get("x-filename", "")) if ch.isprintable())[:200] or None
    try:
        with closing(connect()) as db, db:
            db.execute("INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (report["id"], key, report["created_at"], report.get("media_type", "image"), name,
                        report["verdict"], report["ai_score"], report["sha256"], json.dumps(report)))
            db.execute("""DELETE FROM reports WHERE owner = ? AND id NOT IN
                          (SELECT id FROM reports WHERE owner = ? ORDER BY created_at DESC LIMIT ?)""",
                       (key, key, MAX_PER_OWNER))
    except Exception:
        logger.exception("Report history could not be saved")


def list_reports(request: Request):
    key = owner(request)
    if key is None:
        return []
    with closing(connect()) as db:
        rows = db.execute("""SELECT id, created_at, media_type, filename, verdict, ai_score, sha256 FROM reports
                             WHERE owner = ? ORDER BY created_at DESC""", (key,)).fetchall()
    fields = ("id", "created_at", "media_type", "filename", "verdict", "ai_score", "sha256")
    return [dict(zip(fields, row)) for row in rows]


def get_report(request: Request, report_id: str):
    key = owner(request)
    if key is None:
        return None
    with closing(connect()) as db:
        row = db.execute("SELECT body FROM reports WHERE id = ? AND owner = ?", (report_id, key)).fetchone()
    return json.loads(row[0]) if row else None


def delete_report(request: Request, report_id: str):
    key = owner(request)
    if key is None:
        return False
    with closing(connect()) as db, db:
        return db.execute("DELETE FROM reports WHERE id = ? AND owner = ?", (report_id, key)).rowcount > 0
