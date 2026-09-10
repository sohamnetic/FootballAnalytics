"""
Local Football Analytics product API.

Run: python -m uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.jobs import enqueue, start_worker
from app.store import (
    UPLOADS_DIR,
    ensure_dirs,
    get_match,
    list_matches,
    match_output_dir,
    match_upload_dir,
    now_iso,
    stats_path,
    upsert_match,
)
from config.config import PROJECT_ROOT

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("football.api")

ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024  # 8 GB local prototype
MATCH_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

app = FastAPI(title="Football Analytics", version="mvp-product")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeBody(BaseModel):
    team_a: str = Field(default="Team A", max_length=80)
    team_b: str = Field(default="Team B", max_length=80)
    camera: str = Field(default="Camera 001", max_length=80)
    analysis: str = Field(default="full")  # full | window
    start_time_s: float | None = None
    duration_s: float | None = None


def _valid_id(match_id: str) -> str:
    if not MATCH_ID_RE.match(match_id):
        raise HTTPException(status_code=400, detail="Invalid match id")
    return match_id


def _safe_filename(name: str) -> str:
    raw = Path(name).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(raw).stem)[:80] or "match"
    ext = Path(raw).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Unsupported video format")
    return f"{stem}{ext}"


@app.on_event("startup")
def _startup():
    ensure_dirs()
    start_worker()
    log.info("Football Analytics API ready. project=%s uploads=%s", PROJECT_ROOT, UPLOADS_DIR)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/matches/upload")
async def upload_match(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    filename = _safe_filename(file.filename)
    ext = Path(filename).suffix.lower()
    match_id = str(uuid.uuid4())
    dest_dir = match_upload_dir(match_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"video{ext}"

    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File too large")
                out.write(chunk)
    finally:
        await file.close()

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Empty file")

    record = upsert_match({
        "match_id": match_id,
        "filename": filename,
        "stored_name": dest.name,
        "video_path": str(dest.resolve()),
        "bytes": size,
        "status": "uploaded",
        "progress": 0,
        "stage": "uploaded",
        "message": "Video uploaded.",
        "team_a": "Team A",
        "team_b": "Team B",
        "camera": "Camera 001",
        "analysis": "full",
        "start_time_s": None,
        "duration_s": None,
        "created_at": now_iso(),
        "error": None,
    })
    return {
        "match_id": match_id,
        "filename": filename,
        "status": "uploaded",
        "bytes": size,
        "created_at": record["created_at"],
    }


@app.get("/api/matches")
def matches():
    return {"matches": list_matches()}


@app.get("/api/matches/{match_id}")
def match_detail(match_id: str):
    row = get_match(_valid_id(match_id))
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    return row


@app.post("/api/matches/{match_id}/analyze")
def analyze(match_id: str, body: AnalyzeBody):
    row = get_match(_valid_id(match_id))
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    if row.get("status") in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Analysis already running")

    start_time = 0.0
    duration = None
    analysis = (body.analysis or "full").strip().lower()
    if analysis == "window":
        start_time = float(body.start_time_s or 0)
        duration = body.duration_s
        if duration is None or duration <= 0:
            raise HTTPException(status_code=400, detail="Window analysis needs duration_s")
    elif analysis != "full":
        raise HTTPException(status_code=400, detail="analysis must be full or window")

    upsert_match({
        "match_id": match_id,
        "team_a": body.team_a.strip() or "Team A",
        "team_b": body.team_b.strip() or "Team B",
        "camera": body.camera.strip() or "Camera 001",
        "analysis": analysis,
        "start_time_s": start_time if analysis == "window" else 0,
        "duration_s": duration,
        "error": None,
    })
    enqueue(match_id)
    return {"match_id": match_id, "status": "queued"}


@app.get("/api/matches/{match_id}/status")
def status(match_id: str):
    row = get_match(_valid_id(match_id))
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    return {
        "match_id": row["match_id"],
        "status": row.get("status"),
        "progress": row.get("progress") or 0,
        "stage": row.get("stage") or row.get("status"),
        "message": row.get("message") or "",
        "progress_kind": "stage-based",
        "filename": row.get("filename"),
        "team_a": row.get("team_a"),
        "team_b": row.get("team_b"),
    }


@app.get("/api/matches/{match_id}/stats")
def stats(match_id: str):
    row = get_match(_valid_id(match_id))
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    if row.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Stats not ready")
    path = stats_path(match_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stats file missing")
    import json
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/matches/{match_id}/video")
def video(match_id: str):
    row = get_match(_valid_id(match_id))
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    path = Path(row["video_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video missing")
    return FileResponse(path, media_type="video/mp4", filename=row.get("filename") or path.name)


@app.get("/api/matches/{match_id}/analysis-video")
def analysis_video(match_id: str):
    _valid_id(match_id)
    root = match_output_dir(match_id)
    candidates = [
        root / "teams" / "team_validation.mp4",
        root / "events" / "possession_validation.mp4",
        root / "events" / "shot_validation.mp4",
        root / "tracking" / "match_tracking" / "match.mp4",
    ]
    for path in candidates:
        if path.exists():
            return FileResponse(path, media_type="video/mp4", filename=path.name)
    raise HTTPException(status_code=404, detail="No analysis video available")
