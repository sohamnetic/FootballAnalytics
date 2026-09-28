"""
Football Analytics product API.

Run locally: python -m uvicorn app.main:app --reload --port 8000
Cloud setup (Vercel + Render + Backblaze B2 + Kaggle): docs/DEPLOY.md
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
import re
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app import jobs, settings
from app.auth import authenticate, create_user, issue_token, parse_token
from app.storage import LocalStorage, StorageUnavailable, get_storage
from app.store import (
    ANALYSIS_VIDEO_FILE,
    STATS_FILE,
    delete_match,
    ensure_loaded,
    fail_interrupted_jobs,
    get_match,
    list_matches,
    now_iso,
    result_key,
    storage_used_bytes,
    upload_key,
    upsert_match,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("football.api")

ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv"}
CONTENT_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo", ".mkv": "video/x-matroska"}
MATCH_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PART_BYTES = settings.UPLOAD_PART_BYTES

app = FastAPI(title="TactiVision", version="mvp-product")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=settings.ALLOWED_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)


class AnalyzeBody(BaseModel):
    team_a: str = Field(default="Team A", max_length=80)
    team_b: str = Field(default="Team B", max_length=80)
    camera: str = Field(default="Camera 001", max_length=80)
    analysis: str = Field(default="full")  # full | window
    start_time_s: float | None = None
    duration_s: float | None = None


class AuthBody(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=120)
    name: str = Field(default="", max_length=80)


class UploadStart(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    duration_s: float | None = Field(default=None, ge=0)  # as the browser read it


class UploadPart(BaseModel):
    number: int = Field(ge=1, le=10000)
    etag: str = Field(max_length=200)


class UploadFinish(BaseModel):
    upload_id: str = Field(max_length=1024)
    parts: list[UploadPart]


def current_user(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> dict:
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
    elif token:
        raw = token.strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Please sign in")
    try:
        return parse_token(raw)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Please sign in again") from exc


def _valid_id(match_id: str) -> str:
    if not MATCH_ID_RE.match(match_id):
        raise HTTPException(status_code=400, detail="Invalid match id")
    return match_id


def _my_match(match_id: str, user: dict) -> dict:
    row = get_match(_valid_id(match_id))
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    if row.get("user_id") not in (None, "", user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed")
    return row


def _safe_filename(name: str) -> str:
    raw = Path(name).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(raw).stem)[:80] or "match"
    ext = Path(raw).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Unsupported video format")
    return f"{stem}{ext}"


def _client(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _has_analysis_video(row: dict) -> bool:
    if "has_analysis_video" in row:
        return bool(row["has_analysis_video"])
    return bool(get_storage().size(result_key(row["match_id"], ANALYSIS_VIDEO_FILE)))


def _has_source_video(row: dict) -> bool:
    return bool(row.get("video_key")) and not row.get("source_deleted") and row.get("status") != "uploading"


STORAGE_DOWN = ("Storage can't be read right now. On the free plan this usually means today's "
                "download limit is used up; it resets at midnight GMT (5:30 AM in India).")


@app.exception_handler(StorageUnavailable)
def _storage_down(request: Request, exc: StorageUnavailable):
    log.warning("Storage read refused: %s", exc)
    return JSONResponse(status_code=503, content={"detail": STORAGE_DOWN})


@app.on_event("startup")
def _startup():
    # start even if storage refuses reads for now; requests get a clear 503
    # until it works again, and the data loads on the first request after
    try:
        ensure_loaded()
    except StorageUnavailable as exc:
        log.warning("Storage not readable at startup, will retry: %s", exc)
    else:
        if settings.RUNNER == "local":
            stuck = fail_interrupted_jobs()
            if stuck:
                log.warning("Marked %d interrupted analysis job(s) as failed", stuck)
    jobs.start_background()
    storage = get_storage()
    if hasattr(storage, "ensure_cors") and settings.BUCKET_ORIGINS:
        if not storage.ensure_cors(settings.BUCKET_ORIGINS):
            log.warning("Couldn't set CORS on the bucket; see docs/DEPLOY.md")
    log.info("API ready. storage=%s runner=%s", settings.STORAGE, settings.RUNNER)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- accounts

@app.post("/api/auth/signup")
def signup(body: AuthBody):
    try:
        user = create_user(body.email, body.password, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "token": issue_token(user)}


@app.post("/api/auth/login")
def login(body: AuthBody, request: Request):
    try:
        user = authenticate(body.email, body.password, _client(request))
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"user": user, "token": issue_token(user)}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {"user": user}


# ---------------------------------------------------------------- uploads
# The browser sends the video straight to storage in parts:
#   1. POST /api/matches/uploads          -> match id + one link per part
#   2. PUT each part to its link          (the bucket, or /api/files locally)
#   3. POST /api/matches/{id}/upload/complete with the part ETags

@app.post("/api/matches/uploads")
def start_upload(body: UploadStart, user: dict = Depends(current_user)):
    filename = _safe_filename(body.filename)
    ext = Path(filename).suffix.lower()
    if body.size > settings.MAX_UPLOAD_BYTES:
        limit = settings.MAX_UPLOAD_BYTES / 1024**3
        raise HTTPException(status_code=413, detail=f"Videos can be up to {limit:.0f} GB")
    if settings.STORAGE_LIMIT_BYTES and storage_used_bytes() + body.size > settings.STORAGE_LIMIT_BYTES:
        raise HTTPException(status_code=507, detail="Storage is full. Delete an old match first.")

    match_id = str(uuid.uuid4())
    key = upload_key(match_id, ext)
    storage = get_storage()
    upload_id = storage.start_upload(key, CONTENT_TYPES[ext])
    count = max(1, math.ceil(body.size / PART_BYTES))
    upsert_match({
        "match_id": match_id,
        "filename": filename,
        "stored_name": Path(key).name,
        "video_key": key,
        "bytes": body.size,
        "video_duration_s": body.duration_s,
        "status": "uploading",
        "progress": 0,
        "stage": "uploading",
        "message": "Uploading video...",
        "team_a": "Team A",
        "team_b": "Team B",
        "camera": "Camera 001",
        "analysis": "full",
        "start_time_s": None,
        "duration_s": None,
        "created_at": now_iso(),
        "error": None,
        "user_id": user["id"],
        "upload_id": upload_id,
    })
    return {
        "match_id": match_id,
        "upload_id": upload_id,
        "part_size": PART_BYTES,
        "urls": [storage.part_url(key, upload_id, n) for n in range(1, count + 1)],
    }


@app.post("/api/matches/{match_id}/upload/complete")
def finish_upload(match_id: str, body: UploadFinish, user: dict = Depends(current_user)):
    row = _my_match(match_id, user)
    if row.get("status") != "uploading" or row.get("upload_id") != body.upload_id:
        raise HTTPException(status_code=409, detail="This upload is not in progress")
    storage = get_storage()
    try:
        storage.finish_upload(row["video_key"], body.upload_id, [p.model_dump() for p in body.parts])
    except Exception as exc:
        log.exception("Could not finish upload %s", match_id)
        raise HTTPException(status_code=400, detail="Upload was incomplete. Please try again.") from exc
    size = storage.size(row["video_key"]) or 0
    if size != row.get("bytes"):
        storage.delete(row["video_key"])
        delete_match(match_id)
        raise HTTPException(status_code=400, detail="Upload was incomplete. Please try again.")
    record = upsert_match({
        "match_id": match_id, "status": "uploaded", "stage": "uploaded",
        "message": "Video uploaded.", "upload_id": None,
    })
    return {"match_id": match_id, "filename": record["filename"], "status": "uploaded",
            "bytes": size, "created_at": record["created_at"]}


@app.post("/api/matches/{match_id}/upload/abort")
def abort_upload(match_id: str, user: dict = Depends(current_user)):
    row = _my_match(match_id, user)
    if row.get("status") == "uploading" and row.get("upload_id"):
        get_storage().abort_upload(row["video_key"], row["upload_id"])
        delete_match(match_id)
    return {"ok": True}


# ---------------------------------------------------------------- matches

@app.get("/api/matches")
def matches(user: dict = Depends(current_user)):
    rows = [r for r in list_matches(user["id"]) if r.get("status") != "uploading"]
    return {"matches": rows}


@app.get("/api/matches/{match_id}")
def match_detail(match_id: str, user: dict = Depends(current_user)):
    return _my_match(match_id, user)


@app.delete("/api/matches/{match_id}")
def remove_match(match_id: str, user: dict = Depends(current_user)):
    row = _my_match(match_id, user)
    if row.get("status") in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Wait until analysis finishes")
    delete_match(match_id)
    return {"ok": True, "match_id": match_id}


@app.post("/api/matches/{match_id}/analyze")
def analyze(match_id: str, body: AnalyzeBody, user: dict = Depends(current_user)):
    row = _my_match(match_id, user)
    if row.get("status") in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Analysis already running")
    if row.get("status") == "uploading":
        raise HTTPException(status_code=409, detail="The upload hasn't finished")
    if row.get("source_deleted"):
        raise HTTPException(status_code=409, detail="The original video was removed after analysis. Upload it again.")

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

    budget = settings.DAILY_DOWNLOAD_BUDGET
    planned = {**row, "analysis": analysis, "duration_s": duration}
    if budget and jobs.estimate_download(planned) > budget:
        raise HTTPException(
            status_code=400,
            detail=(f"This video is too big for the free daily download limit "
                    f"({budget / 1024**2:.0f} MB). Analyse a custom window instead."),
        )

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
    jobs.enqueue(match_id)
    return {"match_id": match_id, "status": "queued"}


@app.get("/api/matches/{match_id}/status")
def status(match_id: str, user: dict = Depends(current_user)):
    row = _my_match(match_id, user)
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
        "log_tail": row.get("log_tail") if row.get("status") == "failed" else None,
    }


@app.get("/api/matches/{match_id}/stats")
def stats(match_id: str, user: dict = Depends(current_user)):
    row = _my_match(match_id, user)
    if row.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Stats not ready")
    payload = get_storage().read_json(result_key(match_id, STATS_FILE))
    if payload is None:
        raise HTTPException(status_code=404, detail="Stats file missing")
    return payload


@app.get("/api/matches/{match_id}/media")
def media(match_id: str, user: dict = Depends(current_user)):
    row = _my_match(match_id, user)
    return {"source_video": _has_source_video(row), "analysis_video": _has_analysis_video(row)}


# The video player can't send headers, so these take ?token= and redirect to
# a short-lived storage link (the bucket serves the bytes, not this API).

@app.get("/api/matches/{match_id}/video")
def video(match_id: str, user: dict = Depends(current_user)):
    row = _my_match(match_id, user)
    if not _has_source_video(row):
        raise HTTPException(status_code=404, detail="Video missing")
    url = get_storage().get_url(row["video_key"], row.get("filename") or "")
    return RedirectResponse(url, status_code=307)


@app.get("/api/matches/{match_id}/analysis-video")
def analysis_video(match_id: str, user: dict = Depends(current_user)):
    row = _my_match(match_id, user)
    if not _has_analysis_video(row):
        raise HTTPException(status_code=404, detail="No analysis video available")
    url = get_storage().get_url(result_key(match_id, ANALYSIS_VIDEO_FILE), "analysis_video.mp4")
    return RedirectResponse(url, status_code=307)


# ---------------------------------------------------------------- local file links
# Stand-ins for the bucket's presigned URLs when FA_STORAGE=local.

def _local_storage() -> LocalStorage:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status_code=404, detail="Not found")
    return storage


def _check(storage: LocalStorage, route: str, method: str, exp: int, sig: str) -> None:
    if not storage.check_link(route, method, exp, sig):
        raise HTTPException(status_code=403, detail="Link expired")


async def _save_body(request: Request, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    md5 = hashlib.md5()
    tmp = dest.with_name(dest.name + ".uploading")
    with tmp.open("wb") as out:
        async for chunk in request.stream():
            md5.update(chunk)
            out.write(chunk)
    tmp.replace(dest)
    return f'"{md5.hexdigest()}"'


@app.put("/api/files/part/{upload_id}/{number}")
async def put_part(upload_id: str, number: int, request: Request, exp: int = 0, sig: str = ""):
    storage = _local_storage()
    _check(storage, f"part/{upload_id}/{number}", "PUT", exp, sig)
    etag = await _save_body(request, storage.part_path(upload_id, number))
    return Response(status_code=200, headers={"ETag": etag})


@app.put("/api/files/{route:path}")
async def put_file(route: str, request: Request, exp: int = 0, sig: str = ""):
    storage = _local_storage()
    _check(storage, route, "PUT", exp, sig)
    etag = await _save_body(request, storage.path(route))
    return Response(status_code=200, headers={"ETag": etag})


@app.get("/api/files/{route:path}")
def get_file(route: str, exp: int = 0, sig: str = "", name: str = ""):
    storage = _local_storage()
    _check(storage, route, "GET", exp, sig)
    path = storage.path(route)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    media_type = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=name or path.name, content_disposition_type="inline")


# ---------------------------------------------------------------- cloud worker

class WorkerBody(BaseModel):
    worker_id: str = Field(min_length=1, max_length=120)


class HeartbeatBody(WorkerBody):
    stage: str | None = Field(default=None, max_length=80)
    progress: int | None = Field(default=None, ge=0, le=100)


class ResultUrlBody(WorkerBody):
    kind: str = Field(pattern="^(stats|video|log)$")


class CompleteBody(WorkerBody):
    summary: dict = Field(default_factory=dict)


class FailBody(WorkerBody):
    message: str = Field(default="We couldn't complete analysis for this match.", max_length=300)
    retry: bool = False
    log_tail: str = Field(default="", max_length=10000)


class ExitBody(WorkerBody):
    reason: str = Field(default="", max_length=40)


def worker_auth(authorization: str | None = Header(default=None)) -> None:
    if not settings.WORKER_TOKEN:
        raise HTTPException(status_code=503, detail="Worker access is not set up")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given.encode(), settings.WORKER_TOKEN.encode()):
        raise HTTPException(status_code=401, detail="Bad worker token")


def _worker_job(match_id: str, worker_id: str) -> dict:
    row = jobs.owned(_valid_id(match_id), worker_id)
    if not row:
        raise HTTPException(status_code=409, detail="This job is no longer yours")
    return row


@app.post("/api/worker/claim", dependencies=[Depends(worker_auth)])
def worker_claim(body: WorkerBody):
    return {"job": jobs.claim(body.worker_id)}


@app.post("/api/worker/jobs/{match_id}/heartbeat", dependencies=[Depends(worker_auth)])
def worker_heartbeat(match_id: str, body: HeartbeatBody):
    return {"ok": jobs.heartbeat(_valid_id(match_id), body.worker_id, body.stage, body.progress)}


@app.post("/api/worker/jobs/{match_id}/upload-url", dependencies=[Depends(worker_auth)])
def worker_upload_url(match_id: str, body: ResultUrlBody):
    _worker_job(match_id, body.worker_id)
    return {"url": jobs.result_upload_url(match_id, body.kind)}


@app.post("/api/worker/jobs/{match_id}/complete", dependencies=[Depends(worker_auth)])
def worker_complete(match_id: str, body: CompleteBody):
    _worker_job(match_id, body.worker_id)
    try:
        jobs.complete(match_id, body.summary)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/worker/jobs/{match_id}/fail", dependencies=[Depends(worker_auth)])
def worker_fail(match_id: str, body: FailBody):
    row = _worker_job(match_id, body.worker_id)
    # the last lines of output, so the failure screen can say what went wrong
    upsert_match({"match_id": match_id, "log_tail": body.log_tail or None}, persist=False)
    if body.retry:
        jobs.requeue_or_fail(row, "worker reported a crash")
    else:
        jobs.fail(match_id, body.message)
    return {"ok": True}


@app.post("/api/worker/exit", dependencies=[Depends(worker_auth)])
def worker_exit(body: ExitBody):
    jobs.worker_exit(body.worker_id, body.reason)
    return {"ok": True}


@app.get("/api/worker/status", dependencies=[Depends(worker_auth)])
def worker_status():
    state = jobs.worker_status()
    state["queued"] = [r["match_id"] for r in list_matches() if r.get("status") == "queued"]
    state["now"] = time.time()
    return state
