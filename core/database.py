# -*- coding: utf-8 -*-
"""
core/database.py — AutoReach v14
SQLite data layer: schema, CRUD, transactions, backup, v13 migration.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, List, Optional

from core.models import (
    AuditLevel, AuditLog, Campaign, CampaignStatus,
    Contact, ContactGroup, Message, MessageStatus, RateWindow,
)

logger = logging.getLogger(__name__)

DB_FILE      = "autoreach.db"
BACKUP_DIR   = "backups"
V13_LOG_FILE = "autoreach_log.json"
V13_BL_FILE  = "blacklist.txt"

# ── Schema DDL ────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS contact_groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    number         TEXT    NOT NULL UNIQUE,
    display_name   TEXT,
    group_id       INTEGER REFERENCES contact_groups(id) ON DELETE SET NULL,
    is_valid       INTEGER NOT NULL DEFAULT 1,
    is_blacklisted INTEGER NOT NULL DEFAULT 0,
    verified_at    TEXT,
    notes          TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS campaigns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'draft',
    scheduled_at    TEXT,
    started_at      TEXT,
    completed_at    TEXT,
    total_contacts  INTEGER NOT NULL DEFAULT 0,
    sent_count      INTEGER NOT NULL DEFAULT 0,
    failed_count    INTEGER NOT NULL DEFAULT 0,
    skipped_count   INTEGER NOT NULL DEFAULT 0,
    daily_limit     INTEGER NOT NULL DEFAULT 30,
    dry_run         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id        INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    contact_id         INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    number             TEXT    NOT NULL,
    message_text       TEXT    NOT NULL,
    status             TEXT    NOT NULL DEFAULT 'queued',
    failure_reason     TEXT,
    retry_count        INTEGER NOT NULL DEFAULT 0,
    max_retries        INTEGER NOT NULL DEFAULT 2,
    queued_at          TEXT,
    sending_at         TEXT,
    sent_at            TEXT,
    failed_at          TEXT,
    skipped_at         TEXT,
    failure_screenshot TEXT,
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(campaign_id, number)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT    NOT NULL DEFAULT 'INFO',
    source      TEXT,
    message_id  INTEGER REFERENCES messages(id)  ON DELETE SET NULL,
    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
    text        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rate_windows (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT    NOT NULL,
    hour       INTEGER NOT NULL,
    sent_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(date, hour)
);

CREATE TABLE IF NOT EXISTS meta (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_campaign ON messages(campaign_id);
CREATE INDEX IF NOT EXISTS idx_messages_number   ON messages(number);
CREATE INDEX IF NOT EXISTS idx_messages_status   ON messages(status);
CREATE INDEX IF NOT EXISTS idx_audit_campaign    ON audit_logs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_audit_created     ON audit_logs(created_at);
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


# ── Database class ────────────────────────────────────────────────────────────

class Database:
    """
    SQLite data layer for AutoReach v14.

    All public methods use explicit transactions with rollback protection.
    The connection is opened once and reused (check_same_thread=False is
    safe here because all writes go through this single class instance,
    protected by the WAL journal mode).
    """

    def __init__(self, db_path: str = DB_FILE) -> None:
        self._path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._apply_schema()
        self._migrate_v13()

    # ── Connection ────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
        self._conn = sqlite3.connect(
            self._path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=30,
        )
        self._conn.row_factory = sqlite3.Row
        logger.info("Database connected: %s", self._path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Database connection closed.")

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager: begin → yield cursor → commit or rollback."""
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN")
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            logger.exception("Transaction rolled back.")
            raise

    def _apply_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)
        logger.debug("Schema applied.")

    # ── Backup ────────────────────────────────────────────────────────────────

    def backup(self, label: str = "", max_keep: int = 10) -> Optional[str]:
        """
        Copy the database file to the backups/ directory.

        Args:
            label:    Short label appended to filename (e.g. 'pre_campaign').
            max_keep: Rotate old backups beyond this count.

        Returns:
            Path of the new backup file, or None on failure.
        """
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix   = f"_{label}" if label else ""
        dst      = os.path.join(BACKUP_DIR, f"autoreach_{ts}{suffix}.db")
        try:
            # Use SQLite's own backup API for consistency
            dest_conn = sqlite3.connect(dst)
            self._conn.backup(dest_conn)
            dest_conn.close()
            logger.info("Database backed up → %s", dst)
            self._rotate_backups(max_keep)
            return dst
        except Exception as exc:
            logger.error("Backup failed: %s", exc)
            return None

    def _rotate_backups(self, max_keep: int) -> None:
        try:
            files = sorted(
                [f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")],
            )
            while len(files) > max_keep:
                old = os.path.join(BACKUP_DIR, files.pop(0))
                os.remove(old)
                logger.debug("Removed old backup: %s", old)
        except Exception as exc:
            logger.warning("Backup rotation error: %s", exc)

    # ── V13 Migration ─────────────────────────────────────────────────────────

    def _migrate_v13(self) -> None:
        """Import v13 JSON history into SQLite on first run (runs once)."""
        cur = self._conn.execute("SELECT value FROM meta WHERE key='v13_migrated'")
        if cur.fetchone():
            return
        if not os.path.exists(V13_LOG_FILE):
            self._set_meta("v13_migrated", "1")
            return

        logger.info("Migrating v13 history from %s …", V13_LOG_FILE)
        # Backup originals first
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(V13_LOG_FILE, os.path.join(BACKUP_DIR, "autoreach_log_v13.json"))
        if os.path.exists(V13_BL_FILE):
            shutil.copy2(V13_BL_FILE, os.path.join(BACKUP_DIR, "blacklist_v13.txt"))

        try:
            with open(V13_LOG_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.error("Cannot read v13 log: %s", exc)
            self._set_meta("v13_migrated", "1")
            return

        sent_entries   = data.get("sent",   [])
        failed_entries = data.get("failed", [])
        total          = len(sent_entries) + len(failed_entries)

        with self._tx() as cur:
            cur.execute(
                "INSERT INTO campaigns(name,message,status,total_contacts,"
                "sent_count,failed_count,completed_at) VALUES(?,?,?,?,?,?,?)",
                ("v13 History Import", "(imported)", "completed",
                 total, len(sent_entries), len(failed_entries), _now()),
            )
            cid = cur.lastrowid

            for e in sent_entries:
                t = e.get("t", _now())
                cur.execute(
                    "INSERT OR IGNORE INTO messages"
                    "(campaign_id,number,message_text,status,sent_at,queued_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (cid, e["n"], "(v13 import)", "sent", t, t, t),
                )

            for e in failed_entries:
                t = e.get("t", _now())
                cur.execute(
                    "INSERT OR IGNORE INTO messages"
                    "(campaign_id,number,message_text,status,failed_at,"
                    "failure_reason,queued_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (cid, e["n"], "(v13 import)", "failed", t,
                     e.get("reason", ""), t, t),
                )

        # Blacklist contacts
        if os.path.exists(V13_BL_FILE):
            with open(V13_BL_FILE, encoding="utf-8") as f:
                bls = [ln.strip() for ln in f if ln.strip()]
            with self._tx() as cur:
                for n in bls:
                    cur.execute(
                        "INSERT OR IGNORE INTO contacts(number,is_blacklisted)"
                        " VALUES(?,1)", (n,),
                    )
                    cur.execute(
                        "UPDATE contacts SET is_blacklisted=1 WHERE number=?", (n,),
                    )

        self._set_meta("v13_migrated", "1")
        logger.info("v13 migration complete: %d sent, %d failed imported.",
                    len(sent_entries), len(failed_entries))

    def _set_meta(self, key: str, value: str) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO meta(key,value,updated_at) VALUES(?,?,?)",
                (key, value, _now()),
            )

    def get_meta(self, key: str) -> Optional[str]:
        cur = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

    # ── Campaign CRUD ─────────────────────────────────────────────────────────

    def create_campaign(self, c: Campaign) -> int:
        """Insert a new campaign, return its assigned id."""
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO campaigns(name,message,status,scheduled_at,"
                "daily_limit,dry_run,total_contacts,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (c.name, c.message, c.status.value,
                 c.scheduled_at.strftime("%Y-%m-%d %H:%M:%S") if c.scheduled_at else None,
                 c.daily_limit, int(c.dry_run), c.total_contacts, _now(), _now()),
            )
            return cur.lastrowid

    def get_campaign(self, campaign_id: int) -> Optional[Campaign]:
        cur = self._conn.execute(
            "SELECT * FROM campaigns WHERE id=?", (campaign_id,))
        row = cur.fetchone()
        return self._row_to_campaign(row) if row else None

    def list_campaigns(self, status: Optional[str] = None) -> List[Campaign]:
        if status:
            cur = self._conn.execute(
                "SELECT * FROM campaigns WHERE status=? ORDER BY created_at DESC",
                (status,))
        else:
            cur = self._conn.execute(
                "SELECT * FROM campaigns ORDER BY created_at DESC")
        return [self._row_to_campaign(r) for r in cur.fetchall()]

    def update_campaign_status(self, campaign_id: int,
                               status: CampaignStatus,
                               **extras) -> None:
        fields = ["status=?", "updated_at=?"]
        vals   = [status.value, _now()]
        if "started_at" in extras:
            fields.append("started_at=?"); vals.append(extras["started_at"])
        if "completed_at" in extras:
            fields.append("completed_at=?"); vals.append(extras["completed_at"])
        vals.append(campaign_id)
        with self._tx() as cur:
            cur.execute(f"UPDATE campaigns SET {', '.join(fields)} WHERE id=?", vals)

    def update_campaign_counts(self, campaign_id: int) -> None:
        """Recalculate sent/failed/skipped from messages table."""
        with self._tx() as cur:
            cur.execute(
                "UPDATE campaigns SET "
                "sent_count=(SELECT COUNT(*) FROM messages WHERE campaign_id=? AND status='sent'),"
                "failed_count=(SELECT COUNT(*) FROM messages WHERE campaign_id=? AND status='failed'),"
                "skipped_count=(SELECT COUNT(*) FROM messages WHERE campaign_id=? AND status='skipped'),"
                "updated_at=? WHERE id=?",
                (campaign_id, campaign_id, campaign_id, _now(), campaign_id),
            )

    def get_recoverable_campaigns(self) -> List[Campaign]:
        """Return campaigns in RUNNING or CRASHED state (interrupted mid-send)."""
        cur = self._conn.execute(
            "SELECT * FROM campaigns WHERE status IN ('running','crashed')"
            " ORDER BY started_at DESC"
        )
        return [self._row_to_campaign(r) for r in cur.fetchall()]

    def _row_to_campaign(self, row: sqlite3.Row) -> Campaign:
        return Campaign(
            id=row["id"], name=row["name"], message=row["message"],
            status=CampaignStatus(row["status"]),
            scheduled_at=_dt(row["scheduled_at"]),
            started_at=_dt(row["started_at"]),
            completed_at=_dt(row["completed_at"]),
            total_contacts=row["total_contacts"],
            sent_count=row["sent_count"],
            failed_count=row["failed_count"],
            skipped_count=row["skipped_count"],
            daily_limit=row["daily_limit"],
            dry_run=bool(row["dry_run"]),
            created_at=_dt(row["created_at"]) or datetime.now(),
            updated_at=_dt(row["updated_at"]) or datetime.now(),
        )

    # ── Message CRUD ──────────────────────────────────────────────────────────

    def bulk_insert_messages(self, messages: List[Message]) -> int:
        """
        Insert messages in a single transaction.
        Duplicate (campaign_id, number) pairs are ignored (UNIQUE constraint).
        Returns count of newly inserted rows.
        """
        inserted = 0
        with self._tx() as cur:
            for m in messages:
                cur.execute(
                    "INSERT OR IGNORE INTO messages"
                    "(campaign_id,contact_id,number,message_text,status,"
                    "retry_count,max_retries,queued_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (m.campaign_id, m.contact_id, m.number, m.message_text,
                     m.status.value, m.retry_count, m.max_retries, _now(), _now()),
                )
                inserted += cur.rowcount
        return inserted

    def get_queued_messages(self, campaign_id: int) -> List[Message]:
        """Return all queued (and sending-state orphans) for a campaign."""
        cur = self._conn.execute(
            "SELECT * FROM messages WHERE campaign_id=?"
            " AND status IN ('queued','sending') ORDER BY id ASC",
            (campaign_id,),
        )
        return [self._row_to_message(r) for r in cur.fetchall()]

    def update_message_status(self, message_id: int,
                               status: MessageStatus,
                               failure_reason: Optional[str] = None,
                               retry_count: Optional[int] = None,
                               screenshot: Optional[str] = None) -> None:
        ts   = _now()
        cols = ["status=?", "updated_at=?"]
        vals: list = [status.value, ts]

        ts_col = {
            MessageStatus.SENDING:  "sending_at",
            MessageStatus.SENT:     "sent_at",
            MessageStatus.FAILED:   "failed_at",
            MessageStatus.SKIPPED:  "skipped_at",
        }.get(status)
        if ts_col:
            cols.append(f"{ts_col}=?"); vals.append(ts)
        if failure_reason is not None:
            cols.append("failure_reason=?"); vals.append(failure_reason)
        if retry_count is not None:
            cols.append("retry_count=?"); vals.append(retry_count)
        if screenshot is not None:
            cols.append("failure_screenshot=?"); vals.append(screenshot)

        vals.append(message_id)
        with self._tx() as cur:
            cur.execute(
                f"UPDATE messages SET {', '.join(cols)} WHERE id=?", vals)

    def get_message(self, message_id: int) -> Optional[Message]:
        cur = self._conn.execute(
            "SELECT * FROM messages WHERE id=?", (message_id,))
        row = cur.fetchone()
        return self._row_to_message(row) if row else None

    def is_duplicate(self, campaign_id: int, number: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM messages WHERE campaign_id=? AND number=? LIMIT 1",
            (campaign_id, number),
        )
        return cur.fetchone() is not None

    def get_campaign_stats(self, campaign_id: int) -> dict:
        cur = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM messages"
            " WHERE campaign_id=? GROUP BY status",
            (campaign_id,),
        )
        stats = {r["status"]: r["cnt"] for r in cur.fetchall()}
        stats["total"] = sum(stats.values())
        return stats

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"], campaign_id=row["campaign_id"],
            contact_id=row["contact_id"], number=row["number"],
            message_text=row["message_text"],
            status=MessageStatus(row["status"]),
            failure_reason=row["failure_reason"],
            retry_count=row["retry_count"], max_retries=row["max_retries"],
            queued_at=_dt(row["queued_at"]),
            sending_at=_dt(row["sending_at"]),
            sent_at=_dt(row["sent_at"]),
            failed_at=_dt(row["failed_at"]),
            skipped_at=_dt(row["skipped_at"]),
            failure_screenshot=row["failure_screenshot"],
            updated_at=_dt(row["updated_at"]) or datetime.now(),
        )

    # ── Contact CRUD ──────────────────────────────────────────────────────────

    def upsert_contact(self, c: Contact) -> int:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO contacts(number,display_name,group_id,"
                "is_valid,is_blacklisted,notes)"
                " VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(number) DO UPDATE SET"
                "   display_name=excluded.display_name,"
                "   group_id=excluded.group_id,"
                "   is_valid=excluded.is_valid,"
                "   is_blacklisted=excluded.is_blacklisted,"
                "   notes=excluded.notes",
                (c.number, c.display_name, c.group_id,
                 int(c.is_valid), int(c.is_blacklisted), c.notes),
            )
            return cur.lastrowid

    def is_blacklisted(self, number: str) -> bool:
        cur = self._conn.execute(
            "SELECT is_blacklisted FROM contacts WHERE number=?", (number,))
        row = cur.fetchone()
        return bool(row["is_blacklisted"]) if row else False

    def set_blacklisted(self, number: str, value: bool = True) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO contacts(number,is_blacklisted) VALUES(?,?)"
                " ON CONFLICT(number) DO UPDATE SET is_blacklisted=excluded.is_blacklisted",
                (number, int(value)),
            )

    def list_contacts(self, group_id: Optional[int] = None,
                      blacklisted: Optional[bool] = None) -> List[Contact]:
        q, p = "SELECT * FROM contacts WHERE 1=1", []
        if group_id is not None:
            q += " AND group_id=?"; p.append(group_id)
        if blacklisted is not None:
            q += " AND is_blacklisted=?"; p.append(int(blacklisted))
        q += " ORDER BY id ASC"
        cur = self._conn.execute(q, p)
        return [self._row_to_contact(r) for r in cur.fetchall()]

    def _row_to_contact(self, row: sqlite3.Row) -> Contact:
        return Contact(
            id=row["id"], number=row["number"],
            display_name=row["display_name"], group_id=row["group_id"],
            is_valid=bool(row["is_valid"]),
            is_blacklisted=bool(row["is_blacklisted"]),
            verified_at=_dt(row["verified_at"]), notes=row["notes"],
        )

    # ── Contact Groups ────────────────────────────────────────────────────────

    def create_group(self, name: str) -> int:
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO contact_groups(name) VALUES(?)", (name,))
            return cur.lastrowid

    def list_groups(self) -> List[ContactGroup]:
        cur = self._conn.execute(
            "SELECT * FROM contact_groups ORDER BY name ASC")
        return [
            ContactGroup(id=r["id"], name=r["name"],
                         created_at=_dt(r["created_at"]) or datetime.now())
            for r in cur.fetchall()
        ]

    # ── Audit Log ─────────────────────────────────────────────────────────────

    def log(self, level: AuditLevel, text: str,
            source: Optional[str] = None,
            message_id: Optional[int] = None,
            campaign_id: Optional[int] = None) -> None:
        """Write a structured audit log entry (never raises)."""
        try:
            with self._tx() as cur:
                cur.execute(
                    "INSERT INTO audit_logs"
                    "(level,source,message_id,campaign_id,text,created_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (level.value, source, message_id, campaign_id,
                     text, _now()),
                )
        except Exception as exc:
            logger.error("Failed to write audit log: %s", exc)

    def query_audit_logs(self, campaign_id: Optional[int] = None,
                         level: Optional[str] = None,
                         search: Optional[str] = None,
                         limit: int = 500,
                         offset: int = 0) -> List[AuditLog]:
        q, p = "SELECT * FROM audit_logs WHERE 1=1", []
        if campaign_id is not None:
            q += " AND campaign_id=?"; p.append(campaign_id)
        if level:
            q += " AND level=?"; p.append(level)
        if search:
            q += " AND text LIKE ?"; p.append(f"%{search}%")
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        p += [limit, offset]
        cur = self._conn.execute(q, p)
        return [
            AuditLog(id=r["id"], level=AuditLevel(r["level"]),
                     text=r["text"], source=r["source"],
                     message_id=r["message_id"], campaign_id=r["campaign_id"],
                     created_at=_dt(r["created_at"]) or datetime.now())
            for r in cur.fetchall()
        ]

    # ── Rate Limiting ─────────────────────────────────────────────────────────

    def increment_rate_window(self) -> int:
        """Increment current hour's counter. Returns new count."""
        date = datetime.now().strftime("%Y-%m-%d")
        hour = datetime.now().hour
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO rate_windows(date,hour,sent_count) VALUES(?,?,1)"
                " ON CONFLICT(date,hour) DO UPDATE SET sent_count=sent_count+1",
                (date, hour),
            )
        cur2 = self._conn.execute(
            "SELECT sent_count FROM rate_windows WHERE date=? AND hour=?",
            (date, hour),
        )
        row = cur2.fetchone()
        return row["sent_count"] if row else 1

    def sent_today(self) -> int:
        date = datetime.now().strftime("%Y-%m-%d")
        cur  = self._conn.execute(
            "SELECT COALESCE(SUM(sent_count),0) as total"
            " FROM rate_windows WHERE date=?", (date,))
        return cur.fetchone()["total"]

    def sent_this_hour(self) -> int:
        date = datetime.now().strftime("%Y-%m-%d")
        hour = datetime.now().hour
        cur  = self._conn.execute(
            "SELECT sent_count FROM rate_windows WHERE date=? AND hour=?",
            (date, hour),
        )
        row = cur.fetchone()
        return row["sent_count"] if row else 0

    # ── Dashboard Aggregates ──────────────────────────────────────────────────

    def global_stats(self) -> dict:
        """Return aggregate counts across all campaigns."""
        cur = self._conn.execute(
            "SELECT "
            " COUNT(*) AS total,"
            " SUM(CASE WHEN status='sent'    THEN 1 ELSE 0 END) AS sent,"
            " SUM(CASE WHEN status='failed'  THEN 1 ELSE 0 END) AS failed,"
            " SUM(CASE WHEN status='queued'  THEN 1 ELSE 0 END) AS queued,"
            " SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) AS skipped,"
            " SUM(CASE WHEN status='sending' THEN 1 ELSE 0 END) AS sending"
            " FROM messages"
        )
        row = cur.fetchone()
        d   = dict(row)
        attempted = (d.get("sent") or 0) + (d.get("failed") or 0)
        d["success_rate"] = round(
            d["sent"] / attempted * 100, 1) if attempted else 0.0
        return d

    def hourly_activity(self, days: int = 1) -> List[dict]:
        """Sent counts per hour for the last N days (for dashboard chart)."""
        cur = self._conn.execute(
            "SELECT date, hour, sent_count FROM rate_windows"
            " WHERE date >= date('now', ? || ' days') ORDER BY date, hour",
            (f"-{days}",),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Factory Reset ─────────────────────────────────────────────────────────

    def factory_reset(self) -> None:
        """Clear all data from the database tables."""
        with self._tx() as cur:
            cur.execute("DELETE FROM messages")
            cur.execute("DELETE FROM campaigns")
            cur.execute("DELETE FROM contacts")
            cur.execute("DELETE FROM contact_groups")
            cur.execute("DELETE FROM audit_logs")
            cur.execute("DELETE FROM rate_windows")
            cur.execute("DELETE FROM meta WHERE key != 'v13_migrated'")
            # Reset sequence counters
            cur.execute("DELETE FROM sqlite_sequence")
        logger.info("Factory reset completed on database.")
