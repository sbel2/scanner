from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .models import Opportunity, ScoredOpportunity

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT,
    summary TEXT,
    deadline TEXT,
    starts_at TEXT,
    location TEXT,
    eligibility_raw TEXT,
    fetched_at TEXT,
    last_scored_at TEXT,
    last_score REAL,
    last_score_json TEXT
);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    item_ids_json TEXT NOT NULL,
    subject TEXT
);

-- Normalized dedup keys of items we've emailed, so the same real-world
-- opportunity is suppressed even when it reappears under a different URL/title.
CREATE TABLE IF NOT EXISTS digest_keys (
    dedup_key TEXT NOT NULL,
    sent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_digest_keys_sent_at ON digest_keys (sent_at);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    items_collected INTEGER DEFAULT 0,
    items_new INTEGER DEFAULT 0,
    items_eligible INTEGER DEFAULT 0,
    items_sent INTEGER DEFAULT 0,
    error TEXT
);
"""


@contextmanager
def connect(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def is_new_or_updated(conn: sqlite3.Connection, opp: Opportunity) -> bool:
    row = conn.execute(
        "SELECT content_hash FROM seen WHERE id = ?", (opp.id,)
    ).fetchone()
    return row is None or row["content_hash"] != opp.content_hash


def mark_seen(conn: sqlite3.Connection, opp: Opportunity) -> None:
    now = datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT INTO seen (id, content_hash, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            content_hash = excluded.content_hash,
            last_seen_at = excluded.last_seen_at
        """,
        (opp.id, opp.content_hash, now, now),
    )


def upsert_opportunity(conn: sqlite3.Connection, scored: ScoredOpportunity) -> None:
    o = scored.opportunity
    conn.execute(
        """
        INSERT INTO opportunities
            (id, title, url, source, category, summary, deadline, starts_at,
             location, eligibility_raw, fetched_at, last_scored_at, last_score, last_score_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            summary = excluded.summary,
            deadline = excluded.deadline,
            starts_at = excluded.starts_at,
            location = excluded.location,
            eligibility_raw = excluded.eligibility_raw,
            last_scored_at = excluded.last_scored_at,
            last_score = excluded.last_score,
            last_score_json = excluded.last_score_json
        """,
        (
            o.id,
            o.title,
            o.url,
            o.source,
            o.category,
            o.summary,
            o.deadline.isoformat() if o.deadline else None,
            o.starts_at.isoformat() if o.starts_at else None,
            o.location,
            o.eligibility_raw,
            o.fetched_at.isoformat(),
            datetime.utcnow().isoformat(),
            scored.final_score,
            json.dumps(
                {
                    "alignment": scored.alignment.model_dump(),
                    "eligibility": scored.eligibility.model_dump(),
                }
            ),
        ),
    )


def record_digest(
    conn: sqlite3.Connection,
    item_ids: list[str],
    subject: str,
    dedup_keys: list[str] | None = None,
) -> None:
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO digests (sent_at, item_ids_json, subject) VALUES (?, ?, ?)",
        (now, json.dumps(item_ids), subject),
    )
    for key in dedup_keys or []:
        if key:
            conn.execute(
                "INSERT INTO digest_keys (dedup_key, sent_at) VALUES (?, ?)",
                (key, now),
            )


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO runs (started_at) VALUES (?)", (datetime.utcnow().isoformat(),)
    )
    return cur.lastrowid


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    collected: int,
    new: int,
    eligible: int,
    sent: int,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE runs SET
            finished_at = ?,
            items_collected = ?,
            items_new = ?,
            items_eligible = ?,
            items_sent = ?,
            error = ?
        WHERE id = ?
        """,
        (datetime.utcnow().isoformat(), collected, new, eligible, sent, error, run_id),
    )


def was_recently_in_digest(conn: sqlite3.Connection, opp_id: str, days: int = 7) -> bool:
    rows = conn.execute(
        "SELECT item_ids_json FROM digests WHERE sent_at >= datetime('now', ?)",
        (f"-{days} days",),
    ).fetchall()
    for row in rows:
        if opp_id in json.loads(row["item_ids_json"]):
            return True
    return False


def was_key_recently_in_digest(conn: sqlite3.Connection, dedup_key: str, days: int = 7) -> bool:
    """True if an opportunity with this normalized dedup key was emailed within
    the window — catches the same event reappearing under a new URL/title."""
    if not dedup_key:
        return False
    row = conn.execute(
        "SELECT 1 FROM digest_keys WHERE dedup_key = ? AND sent_at >= datetime('now', ?) LIMIT 1",
        (dedup_key, f"-{days} days"),
    ).fetchone()
    return row is not None
