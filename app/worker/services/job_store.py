from __future__ import annotations

from decimal import Decimal
from typing import Any

import boto3

from settings import settings
from services.jobs import utc_now

_dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
_table = _dynamodb.Table(settings.JOBS_TABLE_NAME)


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


def mark_running(job_id: str, task_arn: str | None = None) -> None:
    expression = [
        "#status = :status",
        "updated_at = :updated_at",
        "started_at = if_not_exists(started_at, :started_at)",
        "attempt_count = if_not_exists(attempt_count, :zero) + :one",
    ]
    names = {"#status": "status"}
    values = {
        ":status": "running",
        ":updated_at": utc_now(),
        ":started_at": utc_now(),
        ":zero": 0,
        ":one": 1,
    }
    if task_arn:
        expression.append("task_arn = :task_arn")
        values[":task_arn"] = task_arn

    _table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET " + ", ".join(expression) + " REMOVE error_message, error_type",
        ConditionExpression="attribute_exists(job_id)",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def mark_succeeded(
    job_id: str,
    task_arn: str | None,
    output_s3_uri: str,
    summary_s3_uri: str,
) -> None:
    now = utc_now()
    expression = [
        "#status = :status",
        "updated_at = :updated_at",
        "completed_at = :completed_at",
        "output_s3_uri = :output_s3_uri",
        "summary_s3_uri = :summary_s3_uri",
    ]
    values = {
        ":status": "succeeded",
        ":updated_at": now,
        ":completed_at": now,
        ":output_s3_uri": output_s3_uri,
        ":summary_s3_uri": summary_s3_uri,
    }
    if task_arn:
        expression.append("task_arn = :task_arn")
        values[":task_arn"] = task_arn

    _table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET " + ", ".join(expression),
        ConditionExpression="attribute_exists(job_id)",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues=values,
    )


def mark_failed(job_id: str, error_message: str, error_type: str, task_arn: str | None = None) -> None:
    now = utc_now()
    expression = [
        "#status = :status",
        "updated_at = :updated_at",
        "completed_at = :completed_at",
        "error_message = :error_message",
        "error_type = :error_type",
    ]
    values = {
        ":status": "failed",
        ":updated_at": now,
        ":completed_at": now,
        ":error_message": error_message[:4000],
        ":error_type": error_type,
    }
    if task_arn:
        expression.append("task_arn = :task_arn")
        values[":task_arn"] = task_arn

    _table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET " + ", ".join(expression),
        ConditionExpression="attribute_exists(job_id)",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues=values,
    )
