"""Presigned URL/POST helpers for inference artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from services.s3_utils import S3Utils


@dataclass
class PresignedUploadInstructions:
    method: str
    url: str
    fields: dict
    key: str
    expires_in: int


class PresignService:
    def __init__(self):
        self.s3 = S3Utils()

    def create_upload_post(
        self,
        *,
        key: str,
        content_type: str,
        tenant_id: str,
        job_id: str,
    ) -> PresignedUploadInstructions:
        expires_in = int(getattr(settings, "AWS_S3_PRESIGNED_EXPIRES", 3600))
        payload = self.s3.generate_presigned_post(
            s3_key=key,
            expires_in=expires_in,
            content_type=content_type,
            max_size=int(getattr(settings, "INFERENCE_ASYNC_MAX_UPLOAD_BYTES", 2 * 1024 * 1024 * 1024)),
            metadata={
                "tenant_id": str(tenant_id),
                "job_id": str(job_id),
            },
        )
        return PresignedUploadInstructions(
            method="POST",
            url=payload["url"],
            fields=payload.get("fields", {}),
            key=key,
            expires_in=expires_in,
        )

    def create_download_url(self, *, key: str) -> tuple[str, int]:
        expires_in = int(getattr(settings, "AWS_S3_PRESIGNED_EXPIRES", 3600))
        url = self.s3.generate_presigned_url(key, expires_in=expires_in, method="get_object")
        return url, expires_in
