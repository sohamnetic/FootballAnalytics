"""
Where files live. Two backends with the same methods:

  LocalStorage - files under data/, links point back at this API
  S3Storage    - an S3-compatible bucket (Backblaze B2, Cloudflare R2),
                 links are presigned URLs

Keys look like "uploads/<match>/video.mp4" or "results/<match>/match_stats.json".
Videos never pass through the API in the cloud: the browser uploads straight
to the bucket in parts, and the player streams straight from it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import tempfile
import time
import uuid
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode

from app import settings

LINK_TTL_S = 6 * 3600


class StorageUnavailable(Exception):
    """The bucket refused a read (bad key, or the free daily download cap)."""


def _sign(*parts) -> str:
    text = "|".join(str(p) for p in parts)
    return hmac.new(settings.secret().encode(), text.encode(), hashlib.sha256).hexdigest()


class LocalStorage:
    kind = "local"

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"bad key {key!r}")
        return path

    def local_path(self, key: str) -> Path | None:
        return self.path(key)

    def read_json(self, key: str):
        path = self.path(key)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def write_json(self, key: str, data) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)

    def size(self, key: str) -> int | None:
        path = self.path(key)
        return path.stat().st_size if path.is_file() else None

    def put_file(self, key: str, src: Path, content_type: str = "") -> None:
        dest = self.path(key)
        if Path(src).resolve() == dest:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        path = self.path(prefix.rstrip("/"))
        if path == self.root:
            return
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)

    # links (served by the /api/files routes in app/main.py)

    def _link(self, route: str, method: str, name: str = "") -> str:
        exp = int(time.time()) + LINK_TTL_S
        query = {"exp": exp, "sig": _sign(method, route, exp)}
        if name:
            query["name"] = name
        return f"/api/files/{quote(route)}?{urlencode(query)}"

    def check_link(self, route: str, method: str, exp: int, sig: str) -> bool:
        if exp < time.time():
            return False
        return hmac.compare_digest(_sign(method, route, exp), sig)

    def get_url(self, key: str, filename: str = "") -> str:
        return self._link(key, "GET", filename)

    def put_url(self, key: str, content_type: str = "") -> str:
        return self._link(key, "PUT")

    def _parts_dir(self, upload_id: str) -> Path:
        if not upload_id.isalnum():
            raise ValueError("bad upload id")
        return self.root / ".parts" / upload_id

    def start_upload(self, key: str, content_type: str = "") -> str:
        upload_id = uuid.uuid4().hex
        folder = self._parts_dir(upload_id)
        folder.mkdir(parents=True)
        (folder / "key").write_text(key, encoding="utf-8")
        return upload_id

    def part_url(self, key: str, upload_id: str, number: int) -> str:
        return self._link(f"part/{upload_id}/{number}", "PUT")

    def part_path(self, upload_id: str, number: int) -> Path:
        return self._parts_dir(upload_id) / f"{int(number):05d}"

    def finish_upload(self, key: str, upload_id: str, parts: list[dict]) -> None:
        folder = self._parts_dir(upload_id)
        if (folder / "key").read_text(encoding="utf-8") != key:
            raise ValueError("upload does not match key")
        dest = self.path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as out:
            for part in sorted(parts, key=lambda p: p["number"]):
                with self.part_path(upload_id, part["number"]).open("rb") as f:
                    shutil.copyfileobj(f, out, 8 * 1024 * 1024)
        shutil.rmtree(folder, ignore_errors=True)

    def abort_upload(self, key: str, upload_id: str) -> None:
        shutil.rmtree(self._parts_dir(upload_id), ignore_errors=True)


class S3Storage:
    kind = "s3"

    def __init__(self):
        import boto3
        from botocore.config import Config

        if not (settings.S3_ENDPOINT and settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY):
            raise RuntimeError("Set S3_ENDPOINT, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY and S3_BUCKET")
        self.bucket = settings.S3_BUCKET
        self.s3 = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
        )

    def ensure_cors(self, origins: list[str]) -> bool:
        """Let the website PUT upload parts straight into the bucket and read
        the ETag back. Needs a key that may change bucket settings (a B2
        key for all buckets can); otherwise see docs/DEPLOY.md."""
        from botocore.exceptions import ClientError

        rules = [{
            "AllowedOrigins": origins,
            "AllowedMethods": ["GET", "PUT", "HEAD"],
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3600,
        }]
        try:
            current = self.s3.get_bucket_cors(Bucket=self.bucket).get("CORSRules", [])
        except ClientError:
            current = []
        if [{**r, "AllowedOrigins": sorted(r.get("AllowedOrigins", []))} for r in current] == \
                [{**rules[0], "AllowedOrigins": sorted(origins)}]:
            return True
        try:
            self.s3.put_bucket_cors(Bucket=self.bucket, CORSConfiguration={"CORSRules": rules})
            return True
        except ClientError:
            return False

    def _missing(self, exc) -> bool:
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
        return code in ("NoSuchKey", "404", "NotFound")

    def local_path(self, key: str) -> Path | None:
        return None

    def read_json(self, key: str):
        from botocore.exceptions import ClientError

        try:
            body = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if self._missing(exc):
                return None
            # e.g. B2's daily download cap: callers must not treat this as empty
            raise StorageUnavailable(str(exc)) from exc
        return json.loads(body)

    def write_json(self, key: str, data) -> None:
        self.s3.put_object(
            Bucket=self.bucket, Key=key, Body=json.dumps(data, indent=2).encode(),
            ContentType="application/json",
        )

    def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            return int(self.s3.head_object(Bucket=self.bucket, Key=key)["ContentLength"])
        except ClientError as exc:
            if self._missing(exc):
                return None
            raise

    def put_file(self, key: str, src: Path, content_type: str = "") -> None:
        extra = {"ContentType": content_type} if content_type else None
        self.s3.upload_file(str(src), self.bucket, key, ExtraArgs=extra)

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> None:
        if not prefix.strip("/"):
            return
        pages = self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix)
        for page in pages:
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": keys, "Quiet": True})
        uploads = self.s3.list_multipart_uploads(Bucket=self.bucket, Prefix=prefix)
        for item in uploads.get("Uploads", []):
            self.abort_upload(item["Key"], item["UploadId"])

    def get_url(self, key: str, filename: str = "") -> str:
        # no response-content-disposition override: not every S3-compatible
        # store honours it, and videos play inline without it
        params = {"Bucket": self.bucket, "Key": key}
        return self.s3.generate_presigned_url("get_object", Params=params, ExpiresIn=LINK_TTL_S)

    def put_url(self, key: str, content_type: str = "") -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        return self.s3.generate_presigned_url("put_object", Params=params, ExpiresIn=LINK_TTL_S)

    def start_upload(self, key: str, content_type: str = "") -> str:
        extra = {"ContentType": content_type} if content_type else {}
        return self.s3.create_multipart_upload(Bucket=self.bucket, Key=key, **extra)["UploadId"]

    def part_url(self, key: str, upload_id: str, number: int) -> str:
        return self.s3.generate_presigned_url(
            "upload_part",
            Params={"Bucket": self.bucket, "Key": key, "UploadId": upload_id, "PartNumber": int(number)},
            ExpiresIn=LINK_TTL_S,
        )

    def finish_upload(self, key: str, upload_id: str, parts: list[dict]) -> None:
        done = [{"PartNumber": int(p["number"]), "ETag": p["etag"]} for p in sorted(parts, key=lambda p: p["number"])]
        self.s3.complete_multipart_upload(
            Bucket=self.bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": done},
        )

    def abort_upload(self, key: str, upload_id: str) -> None:
        from botocore.exceptions import ClientError

        try:
            self.s3.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
        except ClientError:
            pass


@lru_cache(maxsize=1)
def get_storage():
    if settings.STORAGE == "s3":
        return S3Storage()
    if settings.STORAGE != "local":
        raise RuntimeError(f"Unknown FA_STORAGE={settings.STORAGE!r} (use local or s3)")
    return LocalStorage(settings.DATA_DIR)
