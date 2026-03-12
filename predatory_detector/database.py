from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from werkzeug.security import generate_password_hash, check_password_hash

from .config import DB_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database schema and seed default admins."""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                risk_score REAL NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        # Ensure user_id column exists on older databases
        try:
            conn.execute("SELECT user_id FROM predictions LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE predictions ADD COLUMN user_id INTEGER")

        _seed_admin_if_missing(conn, "Pranav", "Pranav@123")
        _seed_admin_if_missing(conn, "Spandana", "Spandana@123")


def _seed_admin_if_missing(conn: sqlite3.Connection, username: str, password: str) -> None:
    cur = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cur.fetchone() is None:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, 'admin', ?)
            """,
            (username, generate_password_hash(password), datetime.utcnow().isoformat()),
        )


def create_user(username: str, password: str, role: str = "user") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (username, generate_password_hash(password), role, datetime.utcnow().isoformat()),
        )
        return int(cur.lastrowid)


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def verify_user_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_username(username)
    if not user:
        return None
    if not check_password_hash(user["password_hash"], password):
        return None
    return user


def list_users() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY created_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]


def update_user_role(user_id: int, role: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def save_prediction(
    url: str,
    risk_score: float,
    label: str,
    confidence: float,
    user_id: Optional[int] = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO predictions (url, risk_score, label, confidence, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url, risk_score, label, confidence, datetime.utcnow().isoformat(), user_id),
        )


def get_recent_predictions_for_user(user_id: int, limit: int = 25) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT url, risk_score, label, confidence, created_at
            FROM predictions
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


