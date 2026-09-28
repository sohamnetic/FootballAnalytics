"""Runs the analysis pipeline (scripts.pipeline.run_mvp) on one video and
turns its printed output into progress. Used by the local job runner and by
the cloud worker (scripts/cloud/worker.py), so it only needs the standard
library."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]

STAGE_PROGRESS = [
    ("Preparing video", 5, ("Converting video", "Football Analytics - Player Tracking", "Selected device")),
    ("Detecting players", 12, ("Loading YOLO model", "Model loaded")),
    ("Tracking players", 20, ("Running tracking", "Ball detector loaded", "Processed ")),
    ("Detecting ball", 40, ("Tracking Finished", "Ball rows logged")),
    ("Calculating possession", 55, ("Running possession",)),
    ("Assigning teams", 65, ("Running team assignment", "Collecting jersey")),
    ("Analyzing passes", 72, ("Running pass detection",)),
    ("Analyzing turnovers", 80, ("Running interceptions",)),
    ("Analyzing shots", 90, ("Running shot",)),
    ("Generating statistics", 95, ("Building match stats",)),
    ("Rendering video", 97, ("Rendering analysis video",)),
    ("Completed", 100, ("MVP pipeline finished",)),
]

TRACKING_START, TRACKING_END = 20, 40


@dataclass
class PipelineResult:
    ok: bool
    log_path: Path
    stats_path: Path | None = None
    analysis_video: Path | None = None
    summary: dict = field(default_factory=dict)


def tracking_progress(line: str, total: int | None) -> int | None:
    """Progress while tracking runs, from the "Processed N frames" lines."""
    if not total or not line.startswith("Processed "):
        return None
    try:
        done = int(line.split()[1])
    except (IndexError, ValueError):
        return None
    return TRACKING_START + int((TRACKING_END - TRACKING_START) * min(done / total, 1.0))


def match_line(line: str) -> tuple[str, int] | None:
    text = line.strip().lower()
    if not text:
        return None
    for stage, progress, needles in STAGE_PROGRESS:
        if any(needle.lower() in text for needle in needles):
            return stage, progress
    return None


def _command(video: Path, job: dict) -> list[str]:
    cmd = [sys.executable, "-m", "scripts.pipeline.run_mvp", "--video", str(video), "--force-track"]
    start_time = job.get("start_time_s")
    duration = job.get("duration_s") if job.get("analysis") == "window" else None
    cmd.extend(["--start-time", str(float(start_time or 0))])
    if duration not in (None, "", 0):
        cmd.extend(["--duration", str(float(duration))])
    return cmd


def run_pipeline(
    video: Path,
    out_dir: Path,
    job: dict,
    report: Callable[[str, int], None] = lambda stage, progress: None,
    log: Callable[[str], None] = lambda line: None,
) -> PipelineResult:
    """Analyse video into out_dir. report(stage, progress) is called whenever
    either changes; log(line) gets every line the pipeline prints."""
    out_dir = Path(out_dir)
    (out_dir / "analytics").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["FA_OUTPUT_DIR"] = str(out_dir.resolve())
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        _command(video, job),
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    lines: list[str] = []
    total_frames = None
    last = None
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        lines.append(line)
        if len(lines) > 2000:
            del lines[:1000]
        log(line)
        if line.startswith("Frames to process"):
            try:
                total_frames = int(line.split(":")[1])
            except (IndexError, ValueError):
                pass
        tracking = tracking_progress(line, total_frames)
        now = ("Tracking players", tracking) if tracking is not None else match_line(line)
        if now and now != last:
            last = now
            report(*now)

    code = proc.wait()
    log_path = out_dir / "pipeline.log"
    log_path.write_text("\n".join(lines[-600:]), encoding="utf-8")
    if code != 0:
        return PipelineResult(ok=False, log_path=log_path)

    stats = _finalize_stats(out_dir, job)
    if stats is None:
        return PipelineResult(ok=False, log_path=log_path)
    stats_path, summary = stats
    videos = sorted(
        v for v in (out_dir / "analysis").glob("analysis_video*.mp4")
        if v.is_file() and not v.name.endswith(".part.mp4")
    )
    return PipelineResult(
        ok=True,
        log_path=log_path,
        stats_path=stats_path,
        analysis_video=videos[0] if videos else None,
        summary=summary,
    )


def _finalize_stats(out_dir: Path, job: dict) -> tuple[Path, dict] | None:
    """Pick the match stats JSON and stamp the team names on it."""
    analytics = out_dir / "analytics"
    candidates = sorted(
        (p for p in analytics.glob("match_stats*.json") if p.name != "match_stats.json"),
        key=lambda p: p.stat().st_mtime,
    )
    dest = analytics / "match_stats.json"
    if candidates:
        source = candidates[-1]
    elif dest.exists():
        source = dest
    else:
        return None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    meta = payload.setdefault("match", {})
    meta["team_a_name"] = job.get("team_a") or "Team A"
    meta["team_b_name"] = job.get("team_b") or "Team B"
    meta["camera"] = job.get("camera") or "Camera 001"
    meta["match_id"] = job.get("match_id")
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    teams = payload.get("teams", {})
    summary = {
        "goals_a": teams.get("team_a", {}).get("goals"),
        "goals_b": teams.get("team_b", {}).get("goals"),
        "duration_s": meta.get("duration_s") or job.get("duration_s"),
    }
    return dest, summary
