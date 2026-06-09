from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from werkzeug.security import generate_password_hash, check_password_hash

from .config import DB_PATH

# Detect remote PostgreSQL URL
USE_POSTGRES = False
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")):
    USE_POSTGRES = True
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


_POSTGRES_POOL = None

def get_pool():
    global _POSTGRES_POOL
    if _POSTGRES_POOL is None and USE_POSTGRES:
        try:
            from psycopg2.pool import ThreadedConnectionPool
            # Keep between 2 and 20 connections open in the pool
            _POSTGRES_POOL = ThreadedConnectionPool(2, 20, dsn=DATABASE_URL)
        except Exception:
            pass
    return _POSTGRES_POOL


@contextmanager
def get_conn():
    if USE_POSTGRES:
        try:
            import psycopg2
        except ImportError:
            raise ImportError(
                "PostgreSQL support requires 'psycopg2' or 'psycopg2-binary' packages.\n"
                "Please run: pip install psycopg2-binary"
            )
        
        pool = get_pool()
        if pool:
            conn = pool.getconn()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                pool.putconn(conn)
        else:
            conn = psycopg2.connect(DATABASE_URL)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def query_row(conn: Any, sql: str, params: tuple = ()) -> Optional[Any]:
    if USE_POSTGRES:
        import psycopg2.extras
        sql = sql.replace("?", "%s")
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(sql, params)
        return cur.fetchone()
    else:
        cur = conn.execute(sql, params)
        return cur.fetchone()


def query_rows(conn: Any, sql: str, params: tuple = ()) -> List[Any]:
    if USE_POSTGRES:
        import psycopg2.extras
        sql = sql.replace("?", "%s")
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(sql, params)
        return cur.fetchall()
    else:
        cur = conn.execute(sql, params)
        return cur.fetchall()


def execute_write(conn: Any, sql: str, params: tuple = ()) -> None:
    if USE_POSTGRES:
        sql = sql.replace("?", "%s")
        cur = conn.cursor()
        cur.execute(sql, params)
    else:
        conn.execute(sql, params)


def init_db() -> None:
    """Initialize database schema and seed default admins."""
    with get_conn() as conn:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                    created_at TEXT NOT NULL,
                    admin_request TEXT DEFAULT 'none'
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS predictions (
                    id SERIAL PRIMARY KEY,
                    url TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    label TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS directory_listings (
                    id SERIAL PRIMARY KEY,
                    domain TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL CHECK(source IN ('doaj', 'bealls')),
                    name TEXT NOT NULL
                )
                """
            )
        else:
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

            # Ensure admin_request column exists on users table
            try:
                conn.execute("SELECT admin_request FROM users LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE users ADD COLUMN admin_request TEXT DEFAULT 'none'")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS directory_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL CHECK(source IN ('doaj', 'bealls')),
                    name TEXT NOT NULL
                )
                """
            )

        _seed_admin_if_missing(conn, "Pranav", "Pranav@123")
        _seed_admin_if_missing(conn, "Spandana", "Spandana@123")
        _seed_directory_listings_if_empty(conn)


def _seed_admin_if_missing(conn: Any, username: str, password: str) -> None:
    row = query_row(conn, "SELECT id FROM users WHERE username = ?", (username,))
    if row is None:
        execute_write(
            conn,
            """
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, 'admin', ?)
            """,
            (username, generate_password_hash(password), datetime.utcnow().isoformat()),
        )


def create_user(username: str, password: str, role: str = "user") -> int:
    with get_conn() as conn:
        if USE_POSTGRES:
            sql = """
                INSERT INTO users (username, password_hash, role, created_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """
            cur = conn.cursor()
            cur.execute(sql, (username, generate_password_hash(password), role, datetime.utcnow().isoformat()))
            row = cur.fetchone()
            return int(row[0])
        else:
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
        row = query_row(conn, "SELECT * FROM users WHERE username = ?", (username,))
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = query_row(conn, "SELECT * FROM users WHERE id = ?", (user_id,))
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
        rows = query_rows(
            conn,
            "SELECT id, username, role, created_at, admin_request FROM users ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]


def update_user_role(user_id: int, role: str) -> None:
    with get_conn() as conn:
        execute_write(conn, "UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def delete_user_by_id(user_id: int) -> None:
    with get_conn() as conn:
        execute_write(conn, "DELETE FROM predictions WHERE user_id = ?", (user_id,))
        execute_write(conn, "DELETE FROM users WHERE id = ?", (user_id,))


def submit_admin_request(user_id: int) -> None:
    with get_conn() as conn:
        execute_write(conn, "UPDATE users SET admin_request = 'pending' WHERE id = ?", (user_id,))


def handle_admin_request(user_id: int, action: str) -> None:
    with get_conn() as conn:
        if action == 'approve':
            execute_write(conn, "UPDATE users SET role = 'admin', admin_request = 'approved' WHERE id = ?", (user_id,))
        elif action == 'reject':
            execute_write(conn, "UPDATE users SET role = 'user', admin_request = 'rejected' WHERE id = ?", (user_id,))
        elif action == 'revoke':
            execute_write(conn, "UPDATE users SET role = 'user', admin_request = 'none' WHERE id = ?", (user_id,))


def save_prediction(
    url: str,
    risk_score: float,
    label: str,
    confidence: float,
    user_id: Optional[int] = None,
) -> None:
    with get_conn() as conn:
        execute_write(
            conn,
            """
            INSERT INTO predictions (url, risk_score, label, confidence, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url, risk_score, label, confidence, datetime.utcnow().isoformat(), user_id),
        )


def get_recent_predictions_for_user(user_id: int, limit: int = 25) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = query_rows(
            conn,
            """
            SELECT id, url, risk_score, label, confidence, created_at
            FROM predictions
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [dict(r) for r in rows]


def get_all_recent_predictions(limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = query_rows(
            conn,
            """
            SELECT p.id, p.url, p.risk_score, p.label, p.confidence, p.created_at, p.user_id, u.username
            FROM predictions p
            LEFT JOIN users u ON p.user_id = u.id
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in rows]


def delete_prediction_by_id(prediction_id: int) -> None:
    with get_conn() as conn:
        execute_write(conn, "DELETE FROM predictions WHERE id = ?", (prediction_id,))


def clear_predictions_for_user(user_id: int) -> None:
    with get_conn() as conn:
        execute_write(conn, "DELETE FROM predictions WHERE user_id = ?", (user_id,))


def clear_all_predictions() -> None:
    with get_conn() as conn:
        execute_write(conn, "DELETE FROM predictions")


def _seed_directory_listings_if_empty(conn: Any) -> None:
    row = query_row(conn, "SELECT COUNT(*) FROM directory_listings")
    count = row[0] if row else 0
    if count < 600:
        from .seed_data import DOAJ_JOURNALS, BEALLS_JOURNALS
        for domain, name in DOAJ_JOURNALS:
            execute_write(
                conn,
                "INSERT INTO directory_listings (domain, source, name) VALUES (?, 'doaj', ?) ON CONFLICT (domain) DO NOTHING",
                (domain, name),
            )
        for domain, name in BEALLS_JOURNALS:
            execute_write(
                conn,
                "INSERT INTO directory_listings (domain, source, name) VALUES (?, 'bealls', ?) ON CONFLICT (domain) DO NOTHING",
                (domain, name),
            )


def check_directory_listing(domain: str) -> Optional[Dict[str, Any]]:
    """Check database if the domain is listed in DOAJ (whitelist) or Beall's List (blacklist)."""
    domain = domain.strip().lower()

    # Generate domain variations (e.g. ['journals.plos.org', 'plos.org'])
    parts = domain.split('.')
    variations = []
    for i in range(len(parts) - 1):
        variations.append('.'.join(parts[i:]))

    with get_conn() as conn:
        for var in variations:
            row = query_row(conn, "SELECT source, name FROM directory_listings WHERE domain = ?", (var,))
            if row:
                return dict(row)
    return None


def delete_predictions_by_ids(ids: List[int]) -> None:
    if not ids:
        return
    # Build list parameters (e.g. (?, ?, ?))
    placeholders = ",".join(["?"] * len(ids))
    with get_conn() as conn:
        execute_write(conn, f"DELETE FROM predictions WHERE id IN ({placeholders})", tuple(ids))
