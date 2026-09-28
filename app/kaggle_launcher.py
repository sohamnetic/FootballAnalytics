"""
Starts the analysis worker as a private Kaggle notebook (free T4 GPU).

Pushing a notebook to Kaggle runs it. The pushed script is tiny: it clones
this repo at the commit the API is running, then hands over to
scripts/cloud/worker.py, which installs what it needs and works through the
queue. Kaggle can't pass secrets to a pushed notebook, so the API address and
worker token are written into the script; the notebook is private.

Needs KAGGLE_USERNAME and KAGGLE_KEY (from kaggle.com > Settings > API).
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from app import settings

log = logging.getLogger("football.kaggle")

BOOT_SCRIPT = '''\
# Started by the Football Analytics API. Runs the analysis worker on this GPU.
import os
import subprocess
import sys

CONFIG = {config}

os.environ.update(CONFIG["env"])
# not /kaggle/working: whatever is left there is saved as notebook output
work = "/tmp/fa"
subprocess.run(["git", "clone", "--quiet", CONFIG["repo"], work], check=True)
subprocess.run(["git", "-C", work, "checkout", "--quiet", CONFIG["ref"]], check=True)
subprocess.run([sys.executable, "-m", "scripts.cloud.worker", "--setup"], cwd=work, check=True)
'''


def _check_ready() -> None:
    missing = [name for name, value in (
        ("KAGGLE_USERNAME", settings.KAGGLE_USERNAME),
        ("FA_WORKER_TOKEN", settings.WORKER_TOKEN),
        ("FA_PUBLIC_API_URL", settings.PUBLIC_API_URL),
    ) if not value]
    if missing:
        raise RuntimeError("Kaggle worker needs " + ", ".join(missing))


def build_notebook(folder: Path, run_id: str) -> Path:
    config = {
        "repo": settings.GIT_REPO,
        "ref": settings.GIT_REF,
        "env": {
            "FA_API_URL": settings.PUBLIC_API_URL,
            "FA_WORKER_TOKEN": settings.WORKER_TOKEN,
            "FA_WORKER_ID": f"kaggle-{run_id}",
        },
    }
    slug = settings.KAGGLE_KERNEL
    (folder / "worker_boot.py").write_text(
        BOOT_SCRIPT.format(config=json.dumps(config, indent=4)), encoding="utf-8"
    )
    (folder / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{settings.KAGGLE_USERNAME}/{slug}",
        "title": slug,
        "code_file": "worker_boot.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
    }, indent=2), encoding="utf-8")
    return folder


def launch(run_id: str) -> None:
    _check_ready()
    # importing kaggle signs in with KAGGLE_USERNAME / KAGGLE_KEY
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    with tempfile.TemporaryDirectory() as tmp:
        folder = build_notebook(Path(tmp), run_id)
        result = api.kernels_push(str(folder))
    error = getattr(result, "error", None)
    if error:
        raise RuntimeError(f"Kaggle refused the notebook: {error}")
    log.info("Started Kaggle notebook %s/%s run=%s ref=%s",
             settings.KAGGLE_USERNAME, settings.KAGGLE_KERNEL, run_id, settings.GIT_REF)
