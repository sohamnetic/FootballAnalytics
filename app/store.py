"""The list of matches, kept as one JSON file in storage (data/ or the S3 bucket).

The API is the only writer (one Render instance / one local server), so the
list is cached in memory and written back on every change."""

from __future__ import annotations

import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.settings import PROJECT_ROOT
from app.storage import get_storage

INDEX_KEY = "matches_index.json"
MATCHES_OUTPUT = PROJECT_ROOT / "outputs" / "matches"
# progress-only updates are written at most this often
PROGRESS_WRITE_S = 30

_lock = threading.RLock()
_rows: list | None = None
_last_write = 0.0


def upload_key(match_id: str, ext: str) -> str:
    return f"uploads/{match_id}/video{ext}"


def result_key(match_id: str, name: str) -> str:
    return f"results/{match_id}/{name}"


STATS_FILE = "match_stats.json"
ANALYSIS_VIDEO_FILE = "analysis_video.mp4"
LOG_FILE = "pipeline.log"


def match_output_dir(match_id: str) -> Path:
    """Working folder for a local analysis run."""
    return MATCHES_OUTPUT / match_id


def _load() -> list:
    global _rows
    if _rows is None:
        data = get_storage().read_json(INDEX_KEY)
        _rows = data if isinstance(data, list) else []
        for row in _rows:
            # matches uploaded before storage keys existed
            if not row.get("video_key") and row.get("stored_name"):
                row["video_key"] = upload_key(row["match_id"], Path(row["stored_name"]).suffix)
    return _rows


def _save() -> None:
    global _last_write
    get_storage().write_json(INDEX_KEY, _rows)
    _last_write = time.time()


def ensure_loaded() -> None:
    with _lock:
        _load()


def get_match(match_id: str) -> dict | None:
    with _lock:
        for row in _load():
            if row.get("match_id") == match_id:
                return dict(row)
    return None


def upsert_match(record: dict, persist: bool = True) -> dict:
    """Merge record into the match. persist=False is for frequent progress
    updates: they are written at most every PROGRESS_WRITE_S seconds."""
    with _lock:
        rows = _load()
        for i, row in enumerate(rows):
            if row.get("match_id") == record["match_id"]:
                record = {**row, **record}
                rows[i] = record
                break
        else:
            rows.insert(0, record)
        if persist or time.time() - _last_write > PROGRESS_WRITE_S:
            _save()
        return dict(record)


def flush() -> None:
    with _lock:
        if _rows is not None:
            _save()


def list_matches(user_id: str | None = None) -> list:
    with _lock:
        rows = [dict(r) for r in _load()]
    if not user_id:
        return rows
    return [row for row in rows if row.get("user_id") in (user_id, None, "")]


def fail_interrupted_jobs() -> int:
    """For the local runner only: jobs still marked queued/processing died
    with the server. Mark them failed so they can be started again."""
    with _lock:
        stuck = [r for r in _load() if r.get("status") in ("queued", "processing")]
        for r in stuck:
            r.update(
                status="failed",
                stage="Interrupted",
                message="Analysis was interrupted because the server stopped. Start it again.",
                error="interrupted",
            )
        if stuck:
            _save()
    return len(stuck)


def storage_used_bytes() -> int:
    """Rough total of what we keep in storage, from the match records."""
    total = 0
    with _lock:
        for row in _load():
            if not row.get("source_deleted"):
                total += int(row.get("bytes") or 0)
            total += int(row.get("result_bytes") or 0)
    return total


def delete_match(match_id: str) -> bool:
    with _lock:
        rows = _load()
        if not any(r.get("match_id") == match_id for r in rows):
            return False
        rows[:] = [r for r in rows if r.get("match_id") != match_id]
        _save()
    storage = get_storage()
    storage.delete_prefix(f"uploads/{match_id}/")
    storage.delete_prefix(f"results/{match_id}/")
    work = match_output_dir(match_id)
    if work.resolve().parent == MATCHES_OUTPUT.resolve() and work.exists():
        shutil.rmtree(work, ignore_errors=True)
    return True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
