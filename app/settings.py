"""Web app settings. Everything comes from environment variables so the same
code runs on a laptop (defaults) and on Render (see docs/DEPLOY.md)."""

from __future__ import annotations

import os
import secrets as _secrets
from functools import lru_cache
from pathlib import Path

# not from config.config: that imports torch, which the API server doesn't have
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _list(name: str, default: str) -> list[str]:
    return [item.strip().rstrip("/") for item in _env(name, default).split(",") if item.strip()]


DATA_DIR = Path(_env("FA_DATA_DIR") or PROJECT_ROOT / "data")

# local = files under data/, s3 = an S3-compatible bucket (Backblaze B2, R2)
STORAGE = _env("FA_STORAGE", "local").lower().replace("r2", "s3")
# local = analyse on this machine, kaggle = start a Kaggle GPU notebook,
# external = wait for a worker started by hand (scripts/cloud/worker.py)
RUNNER = _env("FA_RUNNER", "local").lower()

ALLOWED_ORIGINS = _list(
    "FA_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
)

# any Vercel site by default, so the site works without copying its address
# here. Safe enough: logins are bearer tokens, not cookies, so another site
# can't act as a signed-in user. Set it to "" to allow only the list above.
ALLOWED_ORIGIN_REGEX = os.environ.get("FA_ALLOWED_ORIGIN_REGEX", r"https://[a-z0-9-]+\.vercel\.app").strip()
# the same for the bucket's CORS rules (S3 allows one * per origin)
BUCKET_ORIGINS = ALLOWED_ORIGINS + (["https://*.vercel.app"] if ALLOWED_ORIGIN_REGEX else [])

# browser uploads go in parts of this size (S3 needs 5 MB+ and at most 10,000 parts)
UPLOAD_PART_BYTES = max(5, int(_env("FA_UPLOAD_PART_MB", "64"))) * 1024 * 1024

MAX_UPLOAD_BYTES = int(float(_env("FA_MAX_UPLOAD_GB", "8")) * 1024**3)
# stop taking uploads once the stored videos reach this (B2 and R2 free tiers are 10 GB)
STORAGE_LIMIT_BYTES = int(float(_env("FA_STORAGE_LIMIT_GB", "9" if STORAGE == "s3" else "0")) * 1024**3)
# delete the uploaded video once the analysis video exists (saves space and downloads)
KEEP_SOURCE_VIDEO = _env("FA_KEEP_SOURCE_VIDEO", "0" if STORAGE == "s3" else "1") == "1"

# Any S3-compatible bucket: Backblaze B2 (free, no card), Cloudflare R2, ...
# B2: S3_ENDPOINT=https://s3.us-east-005.backblazeb2.com S3_REGION=us-east-005
# R2: S3_ENDPOINT=https://<account id>.r2.cloudflarestorage.com (region auto)
_r2_account = _env("R2_ACCOUNT_ID")
S3_ENDPOINT = _env("S3_ENDPOINT") or _env("R2_ENDPOINT") or (
    f"https://{_r2_account}.r2.cloudflarestorage.com" if _r2_account else ""
)
if S3_ENDPOINT and "://" not in S3_ENDPOINT:
    S3_ENDPOINT = f"https://{S3_ENDPOINT}"
S3_REGION = _env("S3_REGION") or (S3_ENDPOINT.split("//")[-1].split(".")[1]
                                   if "backblazeb2.com" in S3_ENDPOINT else "auto")
S3_ACCESS_KEY_ID = _env("S3_ACCESS_KEY_ID") or _env("R2_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = _env("S3_SECRET_ACCESS_KEY") or _env("R2_SECRET_ACCESS_KEY")
S3_BUCKET = _env("S3_BUCKET") or _env("R2_BUCKET", "football-analytics")

# the cloud worker sends this to prove it's ours
WORKER_TOKEN = _env("FA_WORKER_TOKEN")
# address the worker uses to reach this API, e.g. https://tactivision-api.onrender.com
PUBLIC_API_URL = _env("FA_PUBLIC_API_URL") or _env("RENDER_EXTERNAL_URL")
# a job with no word from the worker for this long is treated as dead
WORKER_STALE_S = int(_env("FA_WORKER_STALE_S", "900"))
JOB_MAX_ATTEMPTS = int(_env("FA_JOB_MAX_ATTEMPTS", "2"))

KAGGLE_USERNAME = _env("KAGGLE_USERNAME")
KAGGLE_KERNEL = _env("FA_KAGGLE_KERNEL", "fa-analysis-worker")
# how long a freshly started notebook gets to check in before we start another
KAGGLE_BOOT_S = int(_env("FA_KAGGLE_BOOT_S", "1200"))
GIT_REPO = _env("FA_GIT_REPO", "https://github.com/sohamnetic/FootballAnalytics.git")
# Render sets RENDER_GIT_COMMIT, so the worker runs the same code as the API
GIT_REF = _env("FA_GIT_REF") or _env("RENDER_GIT_COMMIT") or "main"


@lru_cache(maxsize=1)
def secret() -> str:
    """Key used to sign logins and file links."""
    value = _env("FA_SECRET")
    if value:
        return value
    if STORAGE != "local":
        raise RuntimeError("Set FA_SECRET when running in the cloud")
    path = DATA_DIR / "secret.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = _secrets.token_hex(32)
    path.write_text(value, encoding="utf-8")
    return value
