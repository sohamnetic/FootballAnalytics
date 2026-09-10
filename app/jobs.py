"""Background analysis jobs: subprocess into existing run_mvp CLI."""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from config.config import PROJECT_ROOT
from app.store import (
    error_log_path,
    get_match,
    match_output_dir,
    stats_path,
    upsert_match,
)

log = logging.getLogger("football.jobs")

STAGE_PROGRESS = [
    ("Preparing video", 5, ("Football Analytics - Player Tracking", "Selected device")),
    ("Detecting players", 12, ("Loading YOLO model", "Model loaded")),
    ("Tracking players", 20, ("Running tracking", "Ball detector loaded", "Processed ")),
    ("Detecting ball", 40, ("Tracking Finished", "Ball rows logged")),
    ("Calculating possession", 55, ("Running possession",)),
    ("Assigning teams", 65, ("Running team assignment", "Collecting jersey")),
    ("Analyzing passes", 72, ("Running pass detection",)),
    ("Analyzing turnovers", 80, ("Running interceptions",)),
    ("Analyzing shots", 90, ("Running shot",)),
    ("Generating statistics", 98, ("Building match stats",)),
    ("Completed", 100, ("MVP pipeline finished",)),
]

_jobs: queue.Queue[str] = queue.Queue()
_started = False
_start_lock = threading.Lock()


def start_worker():
    global _started
    with _start_lock:
        if _started:
            return
        thread = threading.Thread(target=_worker_loop, name="analysis-worker", daemon=True)
        thread.start()
        _started = True


def enqueue(match_id: str):
    start_worker()
    upsert_match({
        "match_id": match_id,
        "status": "queued",
        "progress": 2,
        "stage": "queued",
        "message": "Waiting to start analysis...",
        "error": None,
    })
    _jobs.put(match_id)


def _match_line(line: str) -> tuple[str, int] | None:
    text = line.strip()
    if not text:
        return None
    for stage, progress, needles in STAGE_PROGRESS:
        if any(needle.lower() in text.lower() for needle in needles):
            return stage, progress
    return None


def _worker_loop():
    while True:
        match_id = _jobs.get()
        try:
            _run_job(match_id)
        except Exception:
            log.exception("Job crashed match_id=%s", match_id)
            _fail(match_id, "Analysis stopped unexpectedly.")
        finally:
            _jobs.task_done()


def _run_job(match_id: str):
    record = get_match(match_id)
    if not record:
        return
    video = Path(record["video_path"])
    if not video.exists():
        _fail(match_id, "Uploaded video is missing.")
        return

    out_dir = match_output_dir(match_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analytics").mkdir(parents=True, exist_ok=True)
    video_dir = out_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    linked = video_dir / video.name
    if not linked.exists():
        try:
            os.link(video, linked)
        except OSError:
            pass

    upsert_match({
        "match_id": match_id,
        "status": "processing",
        "progress": 5,
        "stage": "Preparing video",
        "message": "Analyzing match footage...",
        "error": None,
    })

    cmd = [
        sys.executable,
        "-m",
        "scripts.pipeline.run_mvp",
        "--video",
        str(video),
        "--force-track",
    ]
    start_time = record.get("start_time_s")
    duration = record.get("duration_s")
    if start_time not in (None, "", 0, 0.0):
        cmd.extend(["--start-time", str(start_time)])
    elif start_time == 0 or start_time == 0.0:
        cmd.extend(["--start-time", "0"])
    if duration not in (None, ""):
        cmd.extend(["--duration", str(duration)])

    env = os.environ.copy()
    env["FA_OUTPUT_DIR"] = str(out_dir.resolve())
    env["PYTHONUNBUFFERED"] = "1"

    log.info("Starting pipeline match_id=%s cmd=%s", match_id, cmd)
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    lines = []
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        lines.append(line)
        mapped = _match_line(line)
        if mapped:
            stage, progress = mapped
            upsert_match({
                "match_id": match_id,
                "status": "processing",
                "progress": progress,
                "stage": stage,
                "message": "Analyzing match footage...",
            })
        log.info("[%s] %s", match_id, line)

    code = proc.wait()
    log_path = error_log_path(match_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(lines[-400:]), encoding="utf-8")

    if code != 0:
        log.error("Pipeline failed match_id=%s exit=%s", match_id, code)
        _fail(match_id, "We couldn't complete analysis for this match.")
        return

    if not _finalize_stats(match_id, record, out_dir):
        _fail(match_id, "We couldn't complete analysis for this match.")
        return

    upsert_match({
        "match_id": match_id,
        "status": "completed",
        "progress": 100,
        "stage": "Completed",
        "message": "Analysis complete.",
        "error": None,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })


def _finalize_stats(match_id: str, record: dict, out_dir: Path) -> bool:
    analytics = out_dir / "analytics"
    if not analytics.exists():
        return False
    dest = stats_path(match_id)
    candidates = sorted(analytics.glob("match_stats*.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        return False
    source = dest if dest.exists() else candidates[-1]
    if source != dest:
        shutil.copy2(source, dest)
    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    match_meta = payload.setdefault("match", {})
    match_meta["team_a_name"] = record.get("team_a") or "Team A"
    match_meta["team_b_name"] = record.get("team_b") or "Team B"
    match_meta["camera"] = record.get("camera") or "Camera 001"
    match_meta["match_id"] = match_id
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    goals_a = payload.get("teams", {}).get("team_a", {}).get("goals")
    goals_b = payload.get("teams", {}).get("team_b", {}).get("goals")
    upsert_match({
        "match_id": match_id,
        "goals_a": goals_a,
        "goals_b": goals_b,
        "duration_s": match_meta.get("duration_s") or record.get("duration_s"),
    })
    return dest.exists()


def _fail(match_id: str, user_message: str):
    upsert_match({
        "match_id": match_id,
        "status": "failed",
        "progress": 0,
        "stage": "failed",
        "message": user_message,
        "error": user_message,
    })
