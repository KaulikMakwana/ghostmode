"""
Local SQLite database for GhostMode.
Stores accounts, scan results and delete history.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / ".ghostmode" / "ghostmode.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    _init(con)
    return con


def _init(con: sqlite3.Connection):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS accounts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        service     TEXT    NOT NULL,
        email       TEXT    NOT NULL,
        profile_dir TEXT    NOT NULL,
        active      INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT    NOT NULL,
        last_used   TEXT
    );

    CREATE TABLE IF NOT EXISTS scan_results (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        scanned_at TEXT    NOT NULL,
        results    TEXT    NOT NULL   -- JSON blob: {category: {service: count}}
    );

    CREATE TABLE IF NOT EXISTS delete_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id  INTEGER NOT NULL REFERENCES accounts(id),
        deleted_at  TEXT    NOT NULL,
        service     TEXT    NOT NULL,
        count       INTEGER NOT NULL DEFAULT 0
    );
    """)
    con.commit()


# ── Accounts ──────────────────────────────────────────────────────────────────

def add_account(service: str, email: str, profile_dir: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO accounts (service, email, profile_dir, active, created_at) VALUES (?,?,?,0,?)",
            (service, email, profile_dir, _now()),
        )
        return cur.lastrowid


def list_accounts(service: str = None) -> list[dict]:
    with _conn() as con:
        if service:
            rows = con.execute(
                "SELECT * FROM accounts WHERE service=? ORDER BY id", (service,)
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM accounts ORDER BY service, id").fetchall()
        return [dict(r) for r in rows]


def get_active_account(service: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM accounts WHERE service=? AND active=1", (service,)
        ).fetchone()
        return dict(row) if row else None


def set_active_account(account_id: int):
    with _conn() as con:
        # Get service for this account
        row = con.execute("SELECT service FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not row:
            return
        # Deactivate all in same service, then activate target
        con.execute("UPDATE accounts SET active=0 WHERE service=?", (row["service"],))
        con.execute("UPDATE accounts SET active=1, last_used=? WHERE id=?",
                    (_now(), account_id))
        con.commit()


def delete_account(account_id: int):
    with _conn() as con:
        con.execute("DELETE FROM scan_results WHERE account_id=?", (account_id,))
        con.execute("DELETE FROM delete_history WHERE account_id=?", (account_id,))
        con.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        con.commit()


def touch_account(account_id: int):
    with _conn() as con:
        con.execute("UPDATE accounts SET last_used=? WHERE id=?", (_now(), account_id))
        con.commit()


# ── Scan results ──────────────────────────────────────────────────────────────

def save_scan(account_id: int, results: dict) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO scan_results (account_id, scanned_at, results) VALUES (?,?,?)",
            (account_id, _now(), json.dumps(results)),
        )
        con.commit()
        return cur.lastrowid


def latest_scan(account_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM scan_results WHERE account_id=? ORDER BY id DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        if not row:
            return None
        return {"scanned_at": row["scanned_at"], "results": json.loads(row["results"])}


def scan_history(account_id: int, limit: int = 5) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, scanned_at, results FROM scan_results WHERE account_id=? ORDER BY id DESC LIMIT ?",
            (account_id, limit),
        ).fetchall()
        return [{"id": r["id"], "scanned_at": r["scanned_at"],
                 "results": json.loads(r["results"])} for r in rows]


# ── Delete history ────────────────────────────────────────────────────────────

def save_delete(account_id: int, service: str, count: int):
    with _conn() as con:
        con.execute(
            "INSERT INTO delete_history (account_id, deleted_at, service, count) VALUES (?,?,?,?)",
            (account_id, _now(), service, count),
        )
        con.commit()


def delete_history_summary(account_id: int) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT service, SUM(count) as total, MAX(deleted_at) as last_deleted "
            "FROM delete_history WHERE account_id=? GROUP BY service ORDER BY total DESC",
            (account_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
