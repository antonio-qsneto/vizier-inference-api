from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from settings import settings

_dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
_table = _dynamodb.Table(settings.JOBS_TABLE_NAME)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize(value: Any):
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    return value


def get_job(job_id: str) -> dict[str, Any] | None:
    response = _table.get_item(Key={"job_id": job_id})
    item = response.get("Item")
    if not item:
        return None
    return _normalize(item)


def create_job_record(
    *,
    job_id: str,
    input_s3_uri: str,
    output_s3_uri: str,
    summary_s3_uri: str,
    requested_device: str,
    slice_batch_size: int | None,
    request_id: str,
    correlation_id: str,
    idempotency_key: str | None,
    source: str,
) -> dict[str, Any]:
    now = utc_now()
    item: dict[str, Any] = {
        "job_id": job_id,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "input_s3_uri": input_s3_uri,
        "output_s3_uri": output_s3_uri,
        "summary_s3_uri": summary_s3_uri,
        "requested_device": requested_device,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "source": source,
        "attempt_count": 0,
    }
    if slice_batch_size is not None:
        item["slice_batch_size"] = slice_batch_size
    if idempotency_key:
        item["idempotency_key"] = idempotency_key

    _table.put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(job_id)",
    )
    return item


def create_or_get_job_record(**kwargs) -> tuple[dict[str, Any], bool]:
    try:
        return create_job_record(**kwargs), True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        existing = get_job(kwargs["job_id"])
        if existing is None:
            raise
        return existing, False


def mark_job_failed(job_id: str, error_message: str, error_type: str) -> None:
    now = utc_now()
    _table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=(
            "SET #status = :status, updated_at = :updated_at, completed_at = :completed_at, "
            "error_message = :error_message, error_type = :error_type"
        ),
        ConditionExpression="attribute_exists(job_id)",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "failed",
            ":updated_at": now,
            ":completed_at": now,
            ":error_message": error_message[:4000],
            ":error_type": error_type,
        },
    )
