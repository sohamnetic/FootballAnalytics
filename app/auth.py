"""Local email/password accounts. Not production-grade auth."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path

from config.config import PROJECT_ROOT

USERS_PATH = PROJECT_ROOT / "data" / "users.json"
SECRET_PATH = PROJECT_ROOT / "data" / "secret.txt"
TOKEN_TTL_S = 60 * 60 * 24 * 14

_lock = threading.Lock()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _secret() -> str:
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text(encoding="utf-8").strip()
    value = os.environ.get("FA_SECRET") or secrets.token_hex(32)
    SECRET_PATH.write_text(value, encoding="utf-8")
    return value


def _load_users() -> list:
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not USERS_PATH.exists():
        USERS_PATH.write_text("[]", encoding="utf-8")
    try:
        data = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_users(rows: list) -> None:
    USERS_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()


def _public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row.get("name") or row["email"].split("@")[0],
    }


def create_user(email: str, password: str, name: str = "") -> dict:
    email = email.strip().lower()
    name = (name or "").strip()[:80]
    if not _EMAIL_RE.match(email):
        raise ValueError("Enter a valid email")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    with _lock:
        users = _load_users()
        if any(u.get("email") == email for u in users):
            raise ValueError("An account with this email already exists")
        salt = secrets.token_hex(16)
        row = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": name or email.split("@")[0],
            "salt": salt,
            "password_hash": _hash_password(password, salt),
            "created_at": time.time(),
        }
        users.append(row)
        _save_users(users)
        return _public_user(row)


def authenticate(email: str, password: str) -> dict:
    email = email.strip().lower()
    with _lock:
        users = _load_users()
    for row in users:
        if row.get("email") != email:
            continue
        check = _hash_password(password, row.get("salt", ""))
        if hmac.compare_digest(check, row.get("password_hash", "")):
            return _public_user(row)
    raise ValueError("Invalid email or password")


def get_user(user_id: str) -> dict | None:
    with _lock:
        users = _load_users()
    for row in users:
        if row.get("id") == user_id:
            return _public_user(row)
    return None


def issue_token(user: dict) -> str:
    payload = {
        "uid": user["id"],
        "email": user["email"],
        "exp": int(time.time()) + TOKEN_TTL_S,
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8").hex()
    sig = hmac.new(_secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_token(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid token") from exc
    expect = hmac.new(_secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        raise ValueError("Invalid token")
    payload = json.loads(bytes.fromhex(body).decode("utf-8"))
    if int(payload.get("exp") or 0) < time.time():
        raise ValueError("Session expired")
    user = get_user(str(payload.get("uid")))
    if not user:
        raise ValueError("Account not found")
    return user
