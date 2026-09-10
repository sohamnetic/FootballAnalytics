"""Lightweight on-disk match index for the local product prototype."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from config.config import PROJECT_ROOT

UPLOADS_DIR = PROJECT_ROOT / "data" / "uploads"
MATCHES_OUTPUT = PROJECT_ROOT / "outputs" / "matches"
INDEX_PATH = PROJECT_ROOT / "data" / "matches_index.json"

_lock = threading.Lock()


def ensure_dirs():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    MATCHES_OUTPUT.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        INDEX_PATH.write_text("[]", encoding="utf-8")


def match_upload_dir(match_id: str) -> Path:
    return UPLOADS_DIR / match_id


def match_output_dir(match_id: str) -> Path:
    return MATCHES_OUTPUT / match_id


def stats_path(match_id: str) -> Path:
    return match_output_dir(match_id) / "analytics" / "match_stats.json"


def error_log_path(match_id: str) -> Path:
    return match_output_dir(match_id) / "error.log"


def load_index() -> list:
    ensure_dirs()
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_index(rows: list) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def get_match(match_id: str) -> dict | None:
    with _lock:
        for row in load_index():
            if row.get("match_id") == match_id:
                return dict(row)
    return None


def upsert_match(record: dict) -> dict:
    with _lock:
        rows = load_index()
        found = False
        for i, row in enumerate(rows):
            if row.get("match_id") == record["match_id"]:
                merged = {**row, **record}
                rows[i] = merged
                found = True
                record = merged
                break
        if not found:
            rows.insert(0, record)
        save_index(rows)
        return dict(record)


def list_matches(user_id: str | None = None) -> list:
    with _lock:
        rows = load_index()
    if not user_id:
        return rows
    return [row for row in rows if row.get("user_id") in (user_id, None, "")]


def delete_match(match_id: str) -> bool:
    with _lock:
        rows = load_index()
        row = next((item for item in rows if item.get("match_id") == match_id), None)
        if not row:
            return False
        save_index([item for item in rows if item.get("match_id") != match_id])

    upload_dir = match_upload_dir(match_id)
    output_dir = match_output_dir(match_id)
    _safe_rmtree(upload_dir)
    _safe_rmtree(output_dir)
    return True


def _safe_rmtree(path: Path) -> None:
    import shutil

    try:
        resolved = path.resolve()
    except OSError:
        return
    allowed = (UPLOADS_DIR.resolve(), MATCHES_OUTPUT.resolve())
    if not any(_is_under(resolved, root) for root in allowed):
        return
    if resolved.exists():
        shutil.rmtree(resolved, ignore_errors=True)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
