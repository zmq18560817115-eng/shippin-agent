from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from orchestrator import queue


HASH_NAME = "sha256"
HASH_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must contain at least 8 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(HASH_NAME, password.encode("utf-8"), salt, HASH_ITERATIONS)
    return f"pbkdf2_{HASH_NAME}${HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != f"pbkdf2_{HASH_NAME}":
            return False
        digest = hashlib.pbkdf2_hmac(
            HASH_NAME,
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_user(
    username: str,
    password: str,
    *,
    role: str = "operator",
    display_name: str = "",
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    clean_username = username.strip()
    if not clean_username or len(clean_username) > 64:
        raise ValueError("username must contain 1 to 64 characters")
    if role not in {"operator", "admin"}:
        raise ValueError("role must be operator or admin")
    now = queue.utc_now()
    with queue.get_conn(db_path) as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (username, display_name, password_hash, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean_username, display_name.strip()[:80], hash_password(password), role, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("username already exists") from exc
        user_id = int(cursor.lastrowid)
    return get_user(user_id, db_path=db_path) or {}


def request_registration(
    username: str,
    password: str,
    *,
    display_name: str = "",
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    clean_username = username.strip()
    if not clean_username or len(clean_username) > 64:
        raise ValueError("username must contain 1 to 64 characters")
    now = queue.utc_now()
    with queue.get_conn(db_path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (clean_username,)
        ).fetchone()
        if existing is not None:
            raise ValueError("username already exists")
        try:
            cursor = conn.execute(
                """
                INSERT INTO registration_requests (username, display_name, password_hash, requested_at)
                VALUES (?, ?, ?, ?)
                """,
                (clean_username, display_name.strip()[:80], hash_password(password), now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("a registration request already exists for this username") from exc
        request_id = int(cursor.lastrowid)
    return get_registration_request(request_id, db_path=db_path) or {}


def list_registration_requests(
    *,
    status: str | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM registration_requests"
    values: list[Any] = []
    if status:
        query += " WHERE status = ?"
        values.append(status)
    query += " ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, requested_at DESC"
    with queue.get_conn(db_path) as conn:
        rows = conn.execute(query, values).fetchall()
    return [_public_registration_request(dict(row)) for row in rows]


def get_registration_request(
    request_id: int,
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    with queue.get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM registration_requests WHERE id = ?", (request_id,)).fetchone()
    return _public_registration_request(dict(row)) if row else None


def review_registration_request(
    request_id: int,
    *,
    approve: bool,
    reviewer: str,
    note: str = "",
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    now = queue.utc_now()
    with queue.get_conn(db_path) as conn:
        request = conn.execute(
            "SELECT * FROM registration_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if request is None:
            raise KeyError(request_id)
        if request["status"] != "pending":
            raise ValueError("registration request has already been reviewed")
        if approve:
            existing = conn.execute(
                "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (request["username"],)
            ).fetchone()
            if existing is not None:
                raise ValueError("username already exists")
            conn.execute(
                """
                INSERT INTO users (username, display_name, password_hash, role, created_at, updated_at)
                VALUES (?, ?, ?, 'operator', ?, ?)
                """,
                (request["username"], request["display_name"], request["password_hash"], now, now),
            )
        conn.execute(
            """
            UPDATE registration_requests
            SET status = ?, reviewed_at = ?, reviewed_by = ?, review_note = ?
            WHERE id = ?
            """,
            ("approved" if approve else "rejected", now, reviewer, note.strip()[:300], request_id),
        )
    return get_registration_request(request_id, db_path=db_path) or {}


def authenticate(
    username: str,
    password: str,
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    with queue.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE AND status = 'active'",
            (username.strip(),),
        ).fetchone()
        if row is None or not verify_password(password, str(row["password_hash"])):
            return None
        conn.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (queue.utc_now(), queue.utc_now(), row["id"]),
        )
    return _public_user(dict(row))


def list_users(*, db_path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    with queue.get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY role DESC, status ASC, username COLLATE NOCASE"
        ).fetchall()
    return [_public_user(dict(row)) for row in rows]


def get_user(user_id: int, *, db_path: str | os.PathLike[str] | None = None) -> dict[str, Any] | None:
    with queue.get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _public_user(dict(row)) if row else None


def get_user_by_username(
    username: str,
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    with queue.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
    return _public_user(dict(row)) if row else None


def update_user(
    user_id: int,
    *,
    status: str | None = None,
    password: str | None = None,
    display_name: str | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    if status is not None and status not in {"active", "disabled"}:
        raise ValueError("status must be active or disabled")
    assignments = ["updated_at = ?"]
    values: list[Any] = [queue.utc_now()]
    if status is not None:
        assignments.append("status = ?")
        values.append(status)
    if password:
        assignments.append("password_hash = ?")
        values.append(hash_password(password))
    if display_name is not None:
        assignments.append("display_name = ?")
        values.append(display_name.strip()[:80])
    values.append(user_id)
    with queue.get_conn(db_path) as conn:
        current = conn.execute("SELECT role, status FROM users WHERE id = ?", (user_id,)).fetchone()
        if current is None:
            raise KeyError(user_id)
        if status == "disabled" and current["role"] == "admin" and current["status"] == "active":
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'active'"
            ).fetchone()[0]
            if int(active_admins) <= 1:
                raise ValueError("cannot disable the last active admin")
        changed = conn.execute(
            f"UPDATE users SET {', '.join(assignments)} WHERE id = ?",
            values,
        ).rowcount
    if not changed:
        raise KeyError(user_id)
    return get_user(user_id, db_path=db_path) or {}


def seed_environment_users(*, db_path: str | os.PathLike[str] | None = None) -> None:
    configured = (
        ("VAF_OPERATOR_USER", "VAF_OPERATOR_PASSWORD", "operator"),
        ("VAF_ADMIN_USER", "VAF_ADMIN_PASSWORD", "admin"),
    )
    existing = {user["username"].casefold() for user in list_users(db_path=db_path)}
    for user_key, password_key, role in configured:
        username = str(os.environ.get(user_key) or "").strip()
        password = str(os.environ.get(password_key) or "")
        if username and password and username.casefold() not in existing:
            create_user(username, password, role=role, db_path=db_path)
            existing.add(username.casefold())


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "password_hash"}


def _public_registration_request(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "password_hash"}
