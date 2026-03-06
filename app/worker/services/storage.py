from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from settings import settings

_s3 = boto3.client("s3", region_name=settings.AWS_REGION)


def parse_s3_uri(uri: str) -> tuple[str, str]:
    normalized = str(uri or "").strip()
    if not normalized.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    without_scheme = normalized[5:]
    bucket, _, key = without_scheme.partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {uri}")
    return bucket, key


def object_exists(uri: str) -> bool:
    bucket, key = parse_s3_uri(uri)
    try:
        _s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def generate_presigned_get_url(uri: str) -> str:
    bucket, key = parse_s3_uri(uri)
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=settings.PRESIGNED_URL_EXPIRY_SECONDS,
    )


def generate_presigned_put_url(uri: str, content_type: str) -> str:
    bucket, key = parse_s3_uri(uri)
    return _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=settings.PRESIGNED_URL_EXPIRY_SECONDS,
    )
