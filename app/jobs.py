"""
Starting and tracking analyses.

FA_RUNNER=local     analyse on this machine in a background thread
FA_RUNNER=kaggle    queue the job and start a Kaggle GPU notebook, which runs
                    scripts/cloud/worker.py and talks back through /api/worker
FA_RUNNER=external  same queue, but you start the worker yourself

In the cloud modes the worker claims queued jobs one at a time, sends a
heartbeat while it works, uploads the results straight to storage and then
reports back. A job whose worker goes quiet is put back in the queue.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import settings
from app.pipeline_runner import run_pipeline
from app.storage import get_storage
from app.store import (
    ANALYSIS_VIDEO_FILE,
    LOG_FILE,
    STATS_FILE,
    delete_match,
    get_match,
    list_matches,
    match_output_dir,
    result_key,
    upsert_match,
)

log = logging.getLogger("football.jobs")

RESULT_FILES = {
    "stats": (STATS_FILE, "application/json"),
    "video": (ANALYSIS_VIDEO_FILE, "video/mp4"),
    "log": (LOG_FILE, "text/plain"),
}
WORKER_STATE_KEY = "worker_state.json"
# a worker that hasn't called in this long is gone
WORKER_SEEN_S = 180
PUSH_RETRY_S = 600
NO_GPU_RETRY_S = 3600

_local_jobs: queue.Queue[str] = queue.Queue()
_started = False
_start_lock = threading.Lock()
_state_lock = threading.Lock()
_kick_lock = threading.Lock()
_worker_state: dict | None = None


def _now() -> float:
    return time.time()


def start_background() -> None:
    global _started
    with _start_lock:
        if _started:
            return
        target = _local_loop if settings.RUNNER == "local" else _watchdog_loop
        threading.Thread(target=target, name=f"jobs-{settings.RUNNER}", daemon=True).start()
        _started = True


def enqueue(match_id: str) -> None:
    upsert_match({
        "match_id": match_id,
        "status": "queued",
        "progress": 2,
        "stage": "queued",
        "message": "Waiting to start analysis...",
        "error": None,
        "log_tail": None,
        "attempts": 0,
        "queued_at": _now(),
    })
    if settings.RUNNER == "local":
        start_background()
        _local_jobs.put(match_id)
    else:
        # starting a notebook takes a few seconds, don't hold up the request
        threading.Thread(target=kick, name="kick", daemon=True).start()


def _progress(match_id: str, stage: str, progress: int, previous: dict) -> None:
    changed = stage != previous.get("stage")
    previous["stage"] = stage
    upsert_match({
        "match_id": match_id,
        "status": "processing",
        "progress": min(int(progress), 99),
        "stage": stage,
        "message": "Analyzing match footage...",
        "heartbeat_at": _now(),
    }, persist=changed)


def complete(match_id: str, summary: dict) -> dict:
    """Mark a job done once its stats are in storage."""
    storage = get_storage()
    stats_bytes = storage.size(result_key(match_id, STATS_FILE))
    if not stats_bytes:
        raise FileNotFoundError("match stats were not uploaded")
    video_bytes = storage.size(result_key(match_id, ANALYSIS_VIDEO_FILE)) or 0
    record = get_match(match_id) or {}
    update = {
        "match_id": match_id,
        "status": "completed",
        "progress": 100,
        "stage": "Completed",
        "message": "Analysis complete.",
        "error": None,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "has_analysis_video": bool(video_bytes),
        "result_bytes": stats_bytes + video_bytes,
        "goals_a": summary.get("goals_a"),
        "goals_b": summary.get("goals_b"),
        "duration_s": summary.get("duration_s") or record.get("duration_s"),
    }
    # the analysis video shows the footage too, so the upload can go
    if video_bytes and not settings.KEEP_SOURCE_VIDEO and record.get("video_key"):
        storage.delete(record["video_key"])
        update["source_deleted"] = True
    return upsert_match(update)


def fail(match_id: str, message: str, error: str = "failed") -> None:
    upsert_match({
        "match_id": match_id,
        "status": "failed",
        "progress": 0,
        "stage": "failed",
        "message": message,
        "error": error,
    })


# ---------------------------------------------------------------- local runner

def _local_loop() -> None:
    while True:
        match_id = _local_jobs.get()
        _keep_awake(True)
        try:
            _run_local(match_id)
        except Exception:
            log.exception("Job crashed match_id=%s", match_id)
            fail(match_id, "Analysis stopped unexpectedly.")
        finally:
            _keep_awake(False)
            _local_jobs.task_done()


def _keep_awake(on: bool) -> None:
    """Stop Windows from going to sleep while a job runs (lid close still sleeps)."""
    import sys

    if sys.platform != "win32":
        return
    import ctypes

    es_continuous, es_system_required = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | (es_system_required if on else 0))


def _run_local(match_id: str) -> None:
    record = get_match(match_id)
    if not record:
        return
    storage = get_storage()
    video = storage.local_path(record.get("video_key") or "")
    if not video or not video.exists():
        fail(match_id, "Uploaded video is missing.")
        return

    upsert_match({
        "match_id": match_id, "status": "processing", "progress": 5,
        "stage": "Preparing video", "message": "Analyzing match footage...", "error": None,
    })
    seen: dict = {}
    result = run_pipeline(
        video,
        match_output_dir(match_id),
        {**record, "match_id": match_id},
        report=lambda stage, progress: _progress(match_id, stage, progress, seen),
        log=lambda line: log.info("[%s] %s", match_id, line),
    )
    storage.put_file(result_key(match_id, LOG_FILE), result.log_path, "text/plain")
    if not result.ok:
        lines = result.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
        upsert_match({"match_id": match_id, "log_tail": "\n".join(lines)[-8000:]}, persist=False)
        fail(match_id, result.message or "We couldn't complete analysis for this match.")
        return
    storage.put_file(result_key(match_id, STATS_FILE), result.stats_path, "application/json")
    if result.analysis_video:
        storage.put_file(result_key(match_id, ANALYSIS_VIDEO_FILE), result.analysis_video, "video/mp4")
    complete(match_id, result.summary)


# ------------------------------------------------------------- cloud worker side

def _state() -> dict:
    global _worker_state
    if _worker_state is None:
        _worker_state = get_storage().read_json(WORKER_STATE_KEY) or {}
    return _worker_state


def _save_state(**changes) -> None:
    with _state_lock:
        state = _state()
        state.update(changes)
        try:
            get_storage().write_json(WORKER_STATE_KEY, state)
        except Exception:
            log.exception("Could not save worker state")


def worker_seen(worker_id: str) -> None:
    with _state_lock:
        _state().update(last_seen=_now(), worker_id=worker_id)


def worker_exit(worker_id: str, reason: str = "") -> None:
    if reason == "no_gpu":
        _save_state(last_exit=_now(), no_gpu_at=_now(), worker_id=worker_id)
    else:
        _save_state(last_exit=_now(), worker_id=worker_id)


def worker_status() -> dict:
    with _state_lock:
        return dict(_state())


def _queued() -> list[dict]:
    rows = [r for r in list_matches() if r.get("status") == "queued"]
    return sorted(rows, key=lambda r: r.get("queued_at") or 0)


# ------------------------------------------------------- daily download budget

BUDGET_MESSAGE = ("Waiting for tomorrow's free download allowance. "
                  "It resets at midnight GMT (5:30 AM in India) and the analysis starts then.")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def downloads_today() -> int:
    state = worker_status()
    return int(state.get("dl_bytes") or 0) if state.get("dl_day") == _today() else 0


def estimate_download(row: dict) -> int:
    """Bytes the worker will pull from storage for this job. A window is cut
    out with range requests, so it costs its share of the file."""
    size = int(row.get("bytes") or 0)
    window = float(row.get("duration_s") or 0) if row.get("analysis") == "window" else 0
    total = float(row.get("video_duration_s") or 0)
    if window > 0 and total > 0:
        return min(size, int(size * window / total * 1.2) + 5 * 1024**2)
    return size


def fits_budget(row: dict) -> bool:
    budget = settings.DAILY_DOWNLOAD_BUDGET
    return not budget or downloads_today() + estimate_download(row) <= budget


def _charge(nbytes: int) -> None:
    _save_state(dl_day=_today(), dl_bytes=downloads_today() + nbytes)


def claim(worker_id: str) -> dict | None:
    """Give the worker the oldest queued job that fits today's download budget."""
    worker_seen(worker_id)
    for row in _queued():
        match_id = row["match_id"]
        video_key = row.get("video_key")
        if not video_key or not get_storage().size(video_key):
            fail(match_id, "Uploaded video is missing.")
            continue
        if not fits_budget(row):
            upsert_match({"match_id": match_id, "message": BUDGET_MESSAGE})
            continue
        _charge(estimate_download(row))
        upsert_match({
            "match_id": match_id,
            "status": "processing",
            "progress": 4,
            "stage": "Preparing video",
            "message": "A GPU picked up your match. Downloading the video...",
            "attempts": int(row.get("attempts") or 0) + 1,
            "worker_id": worker_id,
            "heartbeat_at": _now(),
        })
        return {
            "match_id": match_id,
            "video_url": get_storage().get_url(video_key),
            "video_name": Path(video_key).name,
            "job": {k: row.get(k) for k in (
                "team_a", "team_b", "camera", "analysis", "start_time_s", "duration_s")},
        }
    return None


def owned(match_id: str, worker_id: str) -> dict | None:
    row = get_match(match_id)
    if row and row.get("status") == "processing" and row.get("worker_id") == worker_id:
        return row
    return None


def heartbeat(match_id: str, worker_id: str, stage: str | None, progress: int | None) -> bool:
    worker_seen(worker_id)
    row = owned(match_id, worker_id)
    if not row:
        return False
    if stage:
        _progress(match_id, stage, progress or row.get("progress") or 0, {"stage": row.get("stage")})
    else:
        upsert_match({"match_id": match_id, "heartbeat_at": _now()}, persist=False)
    return True


def result_upload_url(match_id: str, kind: str) -> str:
    name, content_type = RESULT_FILES[kind]
    return get_storage().put_url(result_key(match_id, name), content_type)


def requeue_or_fail(row: dict, why: str) -> None:
    if int(row.get("attempts") or 0) < settings.JOB_MAX_ATTEMPTS:
        log.warning("Requeueing %s: %s", row["match_id"], why)
        upsert_match({
            "match_id": row["match_id"], "status": "queued", "progress": 2, "stage": "queued",
            "message": "The analysis machine stopped. Starting again...", "worker_id": None,
        })
    else:
        fail(row["match_id"], "Analysis stopped twice on the cloud GPU. Try again later.", "worker_lost")


def _abandoned_upload(row: dict, now: float) -> bool:
    if row.get("status") != "uploading":
        return False
    try:
        started = datetime.fromisoformat(row["created_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return True
    return now - started > 24 * 3600


def watchdog() -> None:
    now = _now()
    for row in list_matches():
        if _abandoned_upload(row, now):
            if row.get("upload_id"):
                get_storage().abort_upload(row["video_key"], row["upload_id"])
            delete_match(row["match_id"])
        if row.get("status") != "processing":
            continue
        quiet = now - float(row.get("heartbeat_at") or 0)
        if quiet > settings.WORKER_STALE_S:
            requeue_or_fail(row, f"no heartbeat for {quiet:.0f}s")
    kick()


def _watchdog_loop() -> None:
    while True:
        try:
            watchdog()
        except Exception:
            log.exception("Watchdog failed")
        time.sleep(60)


def kick() -> None:
    """Start a Kaggle notebook if jobs are waiting and no worker is running."""
    if settings.RUNNER != "kaggle" or not _kick_lock.acquire(blocking=False):
        return
    try:
        _kick()
    finally:
        _kick_lock.release()


def _kick() -> None:
    waiting = _queued()
    if not waiting:
        return
    # don't start a GPU for jobs that must wait for tomorrow's downloads
    over = [r for r in waiting if not fits_budget(r)]
    for row in over:
        if row.get("message") != BUDGET_MESSAGE:
            upsert_match({"match_id": row["match_id"], "message": BUDGET_MESSAGE})
    waiting = [r for r in waiting if fits_budget(r)]
    if not waiting:
        return
    state = worker_status()
    now = _now()
    last_push = float(state.get("last_push") or 0)
    last_seen = float(state.get("last_seen") or 0)
    last_exit = float(state.get("last_exit") or 0)
    if now - last_seen < WORKER_SEEN_S and last_exit < last_seen:
        return  # a worker is running and will pick the job up
    if state.get("last_push_error"):
        if now - last_push < PUSH_RETRY_S:
            return
    elif now - last_push < settings.KAGGLE_BOOT_S and last_exit < last_push:
        return  # the notebook we started is still booting
    if now - float(state.get("no_gpu_at") or 0) < NO_GPU_RETRY_S:
        for row in waiting:
            upsert_match({"match_id": row["match_id"],
                          "message": "Free GPU hours are used up for now. It will start when they reset."})
        return

    from app.kaggle_launcher import launch

    run_id = uuid.uuid4().hex[:8]
    try:
        launch(run_id)
    except Exception as exc:
        log.exception("Could not start the Kaggle notebook")
        _save_state(last_push=now, last_push_error=str(exc)[:300])
        for row in waiting:
            upsert_match({"match_id": row["match_id"],
                          "message": "Couldn't reach the cloud GPU yet. Retrying in a few minutes..."})
        return
    _save_state(last_push=now, last_push_error=None, run_id=run_id)
    for row in waiting:
        upsert_match({"match_id": row["match_id"],
                      "message": "Starting a cloud GPU. This takes a few minutes..."})
