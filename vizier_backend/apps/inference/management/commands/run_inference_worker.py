"""Run SQS-backed inference worker using Django ORM state."""

from __future__ import annotations

import json
import logging
import os
import time

from django.core.management.base import BaseCommand

from services.queue_service import QueueService

from apps.inference.worker_pipeline import InferenceWorkerPipeline

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consumes SQS inference queue and processes jobs asynchronously"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one message and exit")
        parser.add_argument(
            "--wait-seconds",
            type=int,
            default=int(os.getenv("INFERENCE_WORKER_WAIT_SECONDS", "20")),
            help="SQS long-poll wait time",
        )

    def handle(self, *args, **options):
        once = bool(options.get("once"))
        wait_seconds = int(options.get("wait_seconds") or 20)
        visibility_extension = int(os.getenv("INFERENCE_WORKER_VISIBILITY_EXTENSION", "1800"))

        queue = QueueService()
        pipeline = InferenceWorkerPipeline()

        logger.info(json.dumps({"event": "inference_worker_started", "once": once}))

        while True:
            messages = queue.receive_messages(max_messages=1, wait_seconds=wait_seconds)
            if not messages:
                if once:
                    return
                continue

            msg = messages[0]
            receipt_handle = msg["ReceiptHandle"]
            body = msg.get("Body")

            try:
                payload = json.loads(body or "{}")
                job_id = payload.get("job_id")

                logger.info(
                    json.dumps(
                        {
                            "event": "inference_worker_message_received",
                            "job_id": job_id,
                            "receive_count": msg.get("Attributes", {}).get("ApproximateReceiveCount"),
                        }
                    )
                )

                queue.change_visibility(receipt_handle, visibility_extension)
                started = time.monotonic()
                def _heartbeat():
                    queue.change_visibility(receipt_handle, visibility_extension)

                pipeline.process_message(payload, visibility_heartbeat=_heartbeat)
                elapsed_ms = int((time.monotonic() - started) * 1000)

                queue.delete_message(receipt_handle)
                logger.info(
                    json.dumps(
                        {
                            "event": "inference_worker_message_processed",
                            "job_id": job_id,
                            "elapsed_ms": elapsed_ms,
                        }
                    )
                )

            except Exception:
                logger.exception("inference_worker_message_failed")
                # Let SQS redelivery policy handle retries / DLQ.

            if once:
                return
