"""Email/password accounts, stored as users.json in storage (data/ or the S3 bucket).

Simple on purpose: salted PBKDF2 passwords, HMAC-signed tokens, and a limit
on failed logins so passwords can't be guessed quickly."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid

from app.settings import secret
from app.storage import get_storage

USERS_KEY = "users.json"
TOKEN_TTL_S = 60 * 60 * 24 * 14

# failed logins allowed per email (and per client address) in the window
LOGIN_MAX_FAILS = 8
LOGIN_WINDOW_S = 15 * 60

_lock = threading.Lock()
_users: list | None = None
_fails: dict[str, list[float]] = {}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _load_users() -> list:
    global _users
    if _users is None:
        data = get_storage().read_json(USERS_KEY)
        _users = data if isinstance(data, list) else []
    return _users


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
        get_storage().write_json(USERS_KEY, users)
        return _public_user(row)


def _too_many_fails(*keys: str) -> bool:
    cutoff = time.time() - LOGIN_WINDOW_S
    with _lock:
        for key in keys:
            recent = [t for t in _fails.get(key, []) if t > cutoff]
            _fails[key] = recent
            if len(recent) >= LOGIN_MAX_FAILS:
                return True
    return False


def _note_fail(*keys: str) -> None:
    with _lock:
        for key in keys:
            _fails.setdefault(key, []).append(time.time())


def authenticate(email: str, password: str, client: str = "") -> dict:
    email = email.strip().lower()
    keys = (f"email:{email}", f"ip:{client}") if client else (f"email:{email}",)
    if _too_many_fails(*keys):
        raise PermissionError("Too many failed attempts. Try again in 15 minutes.")
    with _lock:
        users = list(_load_users())
    for row in users:
        if row.get("email") != email:
            continue
        check = _hash_password(password, row.get("salt", ""))
        if hmac.compare_digest(check, row.get("password_hash", "")):
            return _public_user(row)
    _note_fail(*keys)
    raise ValueError("Invalid email or password")


def get_user(user_id: str) -> dict | None:
    with _lock:
        users = list(_load_users())
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
    sig = hmac.new(secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_token(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid token") from exc
    expect = hmac.new(secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        raise ValueError("Invalid token")
    payload = json.loads(bytes.fromhex(body).decode("utf-8"))
    if int(payload.get("exp") or 0) < time.time():
        raise ValueError("Session expired")
    user = get_user(str(payload.get("uid")))
    if not user:
        raise ValueError("Account not found")
    return user
