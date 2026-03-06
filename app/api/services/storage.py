from __future__ import annotations

from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError

from settings import settings

_s3 = boto3.client("s3", region_name=settings.AWS_REGION)


def build_artifact_key(job_id: str, filename: str) -> str:
    prefix = settings.JOB_ARTIFACTS_PREFIX.strip("/")
    return f"{prefix}/{job_id}/{filename}"


def build_job_artifacts(job_id: str) -> dict[str, str]:
    input_key = build_artifact_key(job_id, "input.npz")
    output_key = build_artifact_key(job_id, "output.npz")
    summary_key = build_artifact_key(job_id, "summary.json")
    return {
        "input_key": input_key,
        "output_key": output_key,
        "summary_key": summary_key,
        "input_s3_uri": s3_uri(settings.ARTIFACTS_BUCKET, input_key),
        "output_s3_uri": s3_uri(settings.ARTIFACTS_BUCKET, output_key),
        "summary_s3_uri": s3_uri(settings.ARTIFACTS_BUCKET, summary_key),
    }


def s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key.lstrip('/')}"


def parse_s3_uri(uri: str) -> tuple[str, str]:
    normalized = str(uri or "").strip()
    if not normalized.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")

    without_scheme = normalized[5:]
    bucket, _, key = without_scheme.partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {uri}")
    return bucket, key


def upload_fileobj(fileobj: BinaryIO, bucket: str, key: str, content_type: str) -> None:
    fileobj.seek(0)
    _s3.upload_fileobj(
        fileobj,
        bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )


def object_exists(bucket: str, key: str) -> bool:
    try:
        _s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def get_object(bucket: str, key: str):
    return _s3.get_object(Bucket=bucket, Key=key)


def generate_presigned_get_url(bucket: str, key: str) -> str:
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=settings.PRESIGNED_URL_EXPIRY_SECONDS,
    )
