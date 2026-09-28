"""
Cloud analysis worker. Asks the API for queued matches, analyses each one on
this machine's GPU and uploads the results straight to storage. Exits when
the queue has been empty for a couple of minutes, so a Kaggle notebook stops
using GPU hours as soon as there's nothing to do.

    set FA_API_URL=https://your-api.onrender.com
    set FA_WORKER_TOKEN=...
    python -m scripts.cloud.worker            # laptop / any GPU box
    python -m scripts.cloud.worker --setup    # Kaggle: install packages first
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.pipeline_runner import run_pipeline  # noqa: E402

API = os.environ.get("FA_API_URL", "").rstrip("/")
TOKEN = os.environ.get("FA_WORKER_TOKEN", "")
WORKER_ID = os.environ.get("FA_WORKER_ID") or f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
# Kaggle stops a session after 12 hours, so don't start a match late in one
MAX_UPTIME_S = float(os.environ.get("FA_WORKER_MAX_HOURS", "8")) * 3600
IDLE_EXIT_S = float(os.environ.get("FA_WORKER_IDLE_S", "150"))
HEARTBEAT_S = 60
STARTED = time.time()

# smaller dashboard video: free storage (Backblaze B2) allows 1 GB of downloads a day
os.environ.setdefault("FA_ANALYSIS_VIDEO_WIDTH", "960")
os.environ.setdefault("FA_ANALYSIS_VIDEO_CRF", "28")


def say(msg: str) -> None:
    print(f"[worker {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def call(path: str, payload: dict | None = None, tries: int = 12) -> dict:
    """POST to the API. Retries for a few minutes: a free Render service
    takes about a minute to wake up."""
    body = {"worker_id": WORKER_ID, **(payload or {})}
    for attempt in range(tries):
        try:
            r = requests.post(f"{API}{path}", json=body, timeout=60,
                              headers={"Authorization": f"Bearer {TOKEN}"})
            if r.status_code < 500:
                r.raise_for_status()
                return r.json()
            say(f"{path}: server error {r.status_code}")
        except requests.ConnectionError as exc:
            say(f"{path}: can't reach the API ({exc.__class__.__name__})")
        except requests.Timeout:
            say(f"{path}: timed out")
        time.sleep(min(10 * (attempt + 1), 30))
    raise RuntimeError(f"API unreachable: {path}")


def absolute(url: str) -> str:
    return f"{API}{url}" if url.startswith("/") else url


def setup() -> None:
    """Install what the Kaggle image doesn't have, then fetch model weights."""
    pip = [sys.executable, "-m", "pip", "install", "-q"]
    subprocess.run([*pip, "-r", str(ROOT / "requirements-worker.txt")], check=True)
    # boxmot without its dependencies: we only use its ReID model, and its
    # dependency list drags in a second OpenCV that breaks cv2
    subprocess.run([*pip, "--no-deps", "boxmot==25.0.0"], check=True)
    subprocess.run([sys.executable, "-m", "scripts.download_model"], cwd=ROOT, check=True)


def use_bundled_ffmpeg() -> None:
    if shutil.which("ffmpeg") or os.environ.get("FA_FFMPEG"):
        return
    try:
        import imageio_ffmpeg
    except ImportError:
        return
    os.environ["FA_FFMPEG"] = imageio_ffmpeg.get_ffmpeg_exe()
    say(f"using bundled ffmpeg {os.environ['FA_FFMPEG']}")


def has_gpu() -> bool:
    try:
        import torch
    except ImportError:
        return False
    if torch.cuda.is_available():
        say(f"GPU: {torch.cuda.get_device_name(0)}")
        return True
    return False


class JobError(Exception):
    """A failure with a message for the user; retrying won't help."""


CAP_MESSAGE = ("Today's free storage download limit is used up. "
               "It resets at midnight GMT (5:30 AM in India); start the analysis again after that.")


def _check_response(r: requests.Response) -> None:
    if r.status_code == 403 and "cap" in r.text.lower():
        raise JobError(CAP_MESSAGE)
    r.raise_for_status()


def download(url: str, dest: Path, beat) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(absolute(url), stream=True, timeout=120) as r:
        _check_response(r)
        total = int(r.headers.get("Content-Length") or 0)
        done, last = 0, time.time()
        with dest.open("wb") as f:
            for chunk in r.iter_content(8 * 1024 * 1024):
                f.write(chunk)
                done += len(chunk)
                if time.time() - last > 30:
                    last = time.time()
                    beat()
                    if total:
                        say(f"downloaded {done / total:.0%}")
    if total and done != total:
        raise RuntimeError(f"download stopped at {done} of {total} bytes")
    say(f"downloaded {done / 1e6:.0f} MB")


def fetch_window(url: str, dest: Path, start: float, duration: float) -> bool:
    """Cut just the analysed window out of the stored video. ffmpeg reads
    it with range requests, so only that part is downloaded (free storage
    allows 1 GB of downloads a day). False if ffmpeg couldn't do it."""
    ffmpeg = os.environ.get("FA_FFMPEG") or shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", absolute(url), "-t", f"{duration:.3f}",
           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(dest)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    if "cap" in run.stderr.lower() and "403" in run.stderr:
        raise JobError(CAP_MESSAGE)
    if run.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        say(f"couldn't cut the window ({run.stderr.strip()[-300:]}), downloading the whole video")
        dest.unlink(missing_ok=True)
        return False
    say(f"downloaded the {duration:.0f}s window only ({dest.stat().st_size / 1e6:.0f} MB)")
    return True


def log_tail(path: Path | None, lines: int = 60) -> str:
    if not path or not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])[-8000:]


def upload(match_id: str, kind: str, path: Path, content_type: str) -> None:
    url = call(f"/api/worker/jobs/{match_id}/upload-url", {"kind": kind})["url"]
    with path.open("rb") as f:
        r = requests.put(absolute(url), data=f, timeout=1800, headers={"Content-Type": content_type})
    r.raise_for_status()
    say(f"uploaded {kind} ({path.stat().st_size / 1e6:.1f} MB)")


class Heartbeat:
    """Tells the API we're alive, and sends stage changes as they happen."""

    def __init__(self, match_id: str):
        self.match_id = match_id
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def send(self, stage: str | None = None, progress: int | None = None) -> None:
        with self.lock:
            try:
                call(f"/api/worker/jobs/{self.match_id}/heartbeat",
                     {"stage": stage, "progress": progress}, tries=3)
            except RuntimeError as exc:
                say(str(exc))

    def _loop(self) -> None:
        while not self.stop.wait(HEARTBEAT_S):
            self.send()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()


def run_job(job: dict) -> None:
    match_id = job["match_id"]
    work = Path(tempfile.gettempdir()) / "fa-jobs" / match_id
    shutil.rmtree(work, ignore_errors=True)
    say(f"match {match_id}")
    try:
        with Heartbeat(match_id) as beat:
            settings = dict(job["job"])
            start = float(settings.get("start_time_s") or 0)
            duration = float(settings.get("duration_s") or 0)
            window = work / "window.mp4"
            if settings.get("analysis") == "window" and duration > 0 \
                    and fetch_window(job["video_url"], window, start, duration):
                video = window
                settings["start_time_s"] = 0  # the cut starts at the window
            else:
                video = work / job["video_name"]
                download(job["video_url"], video, beat.send)
            result = run_pipeline(
                video, work / "out", {**settings, "match_id": match_id},
                report=beat.send, log=print,
            )
            upload(match_id, "log", result.log_path, "text/plain")
            if not result.ok:
                call(f"/api/worker/jobs/{match_id}/fail",
                     {"message": "We couldn't complete analysis for this match.",
                      "log_tail": log_tail(result.log_path)})
                return
            beat.send("Saving results", 99)
            upload(match_id, "stats", result.stats_path, "application/json")
            if result.analysis_video:
                upload(match_id, "video", result.analysis_video, "video/mp4")
            call(f"/api/worker/jobs/{match_id}/complete", {"summary": result.summary})
            say(f"match {match_id} done")
    except JobError as exc:
        say(f"match {match_id}: {exc}")
        try:
            call(f"/api/worker/jobs/{match_id}/fail", {"message": str(exc)}, tries=3)
        except RuntimeError:
            pass
    except Exception as exc:
        say(f"match {match_id} crashed: {exc!r}")
        try:
            call(f"/api/worker/jobs/{match_id}/fail",
                 {"message": "Analysis stopped unexpectedly.", "retry": True,
                  "log_tail": traceback.format_exc()[-8000:]}, tries=3)
        except RuntimeError:
            pass
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--setup", action="store_true", help="install packages and models first")
    parser.add_argument("--once", action="store_true", help="exit after one job")
    parser.add_argument("--allow-cpu", action="store_true", help="run even without a GPU (very slow)")
    args = parser.parse_args()
    if not API or not TOKEN:
        sys.exit("Set FA_API_URL and FA_WORKER_TOKEN")

    say(f"worker {WORKER_ID} -> {API}")
    if args.setup:
        setup()
    use_bundled_ffmpeg()
    if not has_gpu() and not args.allow_cpu:
        say("no GPU here (Kaggle GPU hours may be used up), stopping")
        call("/api/worker/exit", {"reason": "no_gpu"})
        return

    idle_since = time.time()
    reason = "idle"
    while True:
        if time.time() - STARTED > MAX_UPTIME_S:
            reason = "uptime"
            break
        job = call("/api/worker/claim").get("job")
        if job:
            run_job(job)
            idle_since = time.time()
            if args.once:
                reason = "once"
                break
            continue
        if time.time() - idle_since > IDLE_EXIT_S:
            break
        time.sleep(15)
    say(f"stopping ({reason})")
    call("/api/worker/exit", {"reason": reason})


if __name__ == "__main__":
    main()
