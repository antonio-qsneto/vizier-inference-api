"""Queue integration for inference jobs."""

from __future__ import annotations

import json
from typing import Any

import boto3
from django.conf import settings


class QueueService:
    def __init__(self):
        self.queue_url = str(getattr(settings, "INFERENCE_JOBS_QUEUE_URL", "") or "").strip()
        if not self.queue_url:
            raise ValueError("INFERENCE_JOBS_QUEUE_URL is not configured")
        self.client = boto3.client("sqs", region_name=settings.AWS_REGION)

    def enqueue_job(self, payload: dict[str, Any]) -> None:
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(payload),
        )

    def receive_messages(self, *, max_messages: int = 1, wait_seconds: int = 20) -> list[dict[str, Any]]:
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max(1, min(10, int(max_messages))),
            WaitTimeSeconds=max(0, min(20, int(wait_seconds))),
            AttributeNames=["ApproximateReceiveCount"],
        )
        return response.get("Messages", [])

    def delete_message(self, receipt_handle: str) -> None:
        self.client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
        )

    def change_visibility(self, receipt_handle: str, timeout_seconds: int) -> None:
        self.client.change_message_visibility(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=max(0, int(timeout_seconds)),
        )
