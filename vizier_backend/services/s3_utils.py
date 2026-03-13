"""AWS S3 utilities for object storage and presigned URLs."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:  # pragma: no cover
    BOTO3_AVAILABLE = False
    ClientError = Exception  # type: ignore


class S3Utils:
    """Thin wrapper around S3 operations used by API/worker."""

    def __init__(self):
        self.bucket = settings.S3_BUCKET
        self.region = settings.AWS_REGION
        self.is_dev_mode = bool(getattr(settings, "S3_LOCAL_DEV_MODE", False))

        if self.is_dev_mode:
            self.storage_root = Path(getattr(settings, "S3_LOCAL_STORAGE_ROOT", "/tmp/vizier-med"))
            self.storage_root.mkdir(parents=True, exist_ok=True)
            self.s3_client = None
            logger.warning(
                "S3Utils running in explicit local dev mode. This must stay disabled in production."
            )
            return

        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for S3 operations")

        if not self.bucket:
            raise ValueError("S3_BUCKET is not configured")

        # Use default AWS credential chain (task role, env, profile, etc.)
        self.s3_client = boto3.client("s3", region_name=self.region)

    def _local_path(self, key: str) -> Path:
        return self.storage_root / str(key).strip("/")

    def upload_file(self, file_path: str, s3_key: str, content_type: str = "application/octet-stream") -> bool:
        try:
            if self.is_dev_mode:
                dst = self._local_path(s3_key)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dst)
                return True

            self.s3_client.upload_file(
                file_path,
                self.bucket,
                s3_key,
                ExtraArgs={"ContentType": content_type},
            )
            return True
        except Exception:
            logger.exception("Failed to upload file", extra={"s3_key": s3_key, "file_path": file_path})
            return False

    def upload_bytes(self, payload: bytes, s3_key: str, content_type: str = "application/octet-stream") -> bool:
        try:
            if self.is_dev_mode:
                dst = self._local_path(s3_key)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(payload)
                return True

            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=payload,
                ContentType=content_type,
            )
            return True
        except Exception:
            logger.exception("Failed to upload bytes", extra={"s3_key": s3_key})
            return False

    def download_file(self, s3_key: str, file_path: str) -> bool:
        try:
            if self.is_dev_mode:
                src = self._local_path(s3_key)
                if not src.exists():
                    return False
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, file_path)
                return True

            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            self.s3_client.download_file(self.bucket, s3_key, file_path)
            return True
        except Exception:
            logger.exception("Failed to download file", extra={"s3_key": s3_key, "file_path": file_path})
            return False

    def generate_presigned_url(self, s3_key: str, expires_in: int = 3600, method: str = "get_object") -> str:
        if self.is_dev_mode:
            path = self._local_path(s3_key)
            if not path.exists():
                raise FileNotFoundError(str(path))
            return f"file://{path}"

        return self.s3_client.generate_presigned_url(
            method,
            Params={"Bucket": self.bucket, "Key": s3_key},
            ExpiresIn=expires_in,
        )

    def generate_presigned_post(
        self,
        *,
        s3_key: str,
        expires_in: int,
        content_type: str,
        min_size: int = 1,
        max_size: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if self.is_dev_mode:
            raise RuntimeError("Presigned POST is unavailable in local dev mode")

        fields: dict[str, str] = {
            "Content-Type": content_type,
        }
        conditions: list[Any] = [
            {"Content-Type": content_type},
            ["content-length-range", int(min_size), int(max_size or getattr(settings, "INFERENCE_ASYNC_MAX_UPLOAD_BYTES", 2 * 1024 * 1024 * 1024))],
        ]

        for key, value in (metadata or {}).items():
            header_name = f"x-amz-meta-{key}"
            fields[header_name] = str(value)
            conditions.append({header_name: str(value)})

        return self.s3_client.generate_presigned_post(
            Bucket=self.bucket,
            Key=s3_key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expires_in,
        )

    def delete_object(self, s3_key: str) -> bool:
        try:
            if self.is_dev_mode:
                path = self._local_path(s3_key)
                if path.exists():
                    os.remove(path)
                return True

            self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception:
            logger.exception("Failed to delete object", extra={"s3_key": s3_key})
            return False

    def object_exists(self, s3_key: str) -> bool:
        try:
            if self.is_dev_mode:
                return self._local_path(s3_key).exists()

            self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception as exc:
            if self.is_dev_mode:
                return False
            if hasattr(exc, "response"):
                code = exc.response.get("Error", {}).get("Code")
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return False
            return False

    def head_object(self, s3_key: str) -> dict[str, Any] | None:
        try:
            if self.is_dev_mode:
                path = self._local_path(s3_key)
                if not path.exists():
                    return None
                return {
                    "ContentLength": path.stat().st_size,
                    "ETag": "",
                }

            return self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
        except ClientError as exc:  # pragma: no cover - depends on AWS
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def get_storage_info(self) -> dict[str, Any]:
        if self.is_dev_mode:
            return {
                "mode": "local-dev",
                "storage_root": str(self.storage_root),
                "bucket": self.bucket,
            }
        return {
            "mode": "s3",
            "bucket": self.bucket,
            "region": self.region,
        }
