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


def list_matches() -> list:
    with _lock:
        return load_index()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
