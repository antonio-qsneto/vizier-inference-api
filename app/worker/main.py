import json
import logging
import time
from threading import Semaphore, Thread

from settings import settings
from services.ecs import run_biomedparse_task, wait_for_task
from services.job_store import get_job, mark_failed, mark_running, mark_succeeded
from services.sqs import change_message_visibility, delete_message, receive_message
from services.storage import (
    generate_presigned_get_url,
    generate_presigned_put_url,
    object_exists,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _task_exit_details(task: dict) -> tuple[int | None, str]:
    containers = task.get("containers", [])
    for container in containers:
        if container.get("name") == settings.BIO_CONTAINER_NAME:
            return container.get("exitCode"), container.get("reason") or task.get("stoppedReason", "")
    return None, task.get("stoppedReason", "")


def main():
    logger.info(json.dumps({"event": "worker_started"}))
    max_concurrency = int(__import__("os").getenv("WORKER_CONCURRENCY", "2"))
    sem = Semaphore(max_concurrency)

    def _handle(msg):
        try:
            process_one(msg)
        finally:
            sem.release()

    while True:
        if not sem.acquire(blocking=False):
            time.sleep(1)
            continue

        msg = receive_message()
        if not msg:
            sem.release()
            time.sleep(1)
            continue

        Thread(target=_handle, args=(msg,), daemon=True).start()


def process_one(msg):
    job_id = msg["job_id"]
    receipt = msg["receipt_handle"]
    task_arn = None

    try:
        job = get_job(job_id)
        if not job:
            raise RuntimeError(f"Job record not found for {job_id}")

        if (
            object_exists(job["output_s3_uri"])
            and object_exists(job["summary_s3_uri"])
            and job.get("status") == "succeeded"
        ):
            logger.info(json.dumps({"event": "job_already_succeeded", "job_id": job_id}))
            delete_message(receipt)
            return

        input_uri = msg["input_s3_uri"]
        output_uri = msg["output_s3_uri"]
        summary_uri = msg["summary_s3_uri"]
        requested_device = msg.get("requested_device") or settings.DEFAULT_REQUESTED_DEVICE
        slice_batch_size = msg.get("slice_batch_size")

        input_download_url = generate_presigned_get_url(input_uri)
        output_upload_url = generate_presigned_put_url(output_uri, "application/octet-stream")
        summary_upload_url = generate_presigned_put_url(summary_uri, "application/json")

        if object_exists(output_uri) and object_exists(summary_uri):
            mark_succeeded(
                job_id,
                task_arn=job.get("task_arn"),
                output_s3_uri=output_uri,
                summary_s3_uri=summary_uri,
            )
            delete_message(receipt)
            logger.info(json.dumps({"event": "job_reconciled_from_existing_artifacts", "job_id": job_id}))
            return

        task_arn = run_biomedparse_task(
            job_id=job_id,
            input_download_url=input_download_url,
            output_upload_url=output_upload_url,
            summary_upload_url=summary_upload_url,
            requested_device=requested_device,
            slice_batch_size=slice_batch_size,
        )
        mark_running(job_id, task_arn=task_arn)
        logger.info(
            json.dumps(
                {
                    "event": "job_running",
                    "job_id": job_id,
                    "task_arn": task_arn,
                    "requested_device": requested_device,
                    "receive_count": msg.get("receive_count"),
                }
            )
        )

        last_visibility_extension = 0.0

        def _heartbeat(_: dict):
            nonlocal last_visibility_extension
            now = time.monotonic()
            if now - last_visibility_extension < max(settings.ECS_TASK_POLL_SECONDS, 30):
                return
            change_message_visibility(receipt, settings.SQS_VISIBILITY_EXTENSION_SECONDS)
            last_visibility_extension = now

        task = wait_for_task(task_arn, on_tick=_heartbeat)
        exit_code, reason = _task_exit_details(task)
        if exit_code not in (0, None):
            raise RuntimeError(f"ECS task exit_code={exit_code}: {reason}")
        if not object_exists(output_uri):
            raise RuntimeError("output.npz was not uploaded")
        if not object_exists(summary_uri):
            raise RuntimeError("summary.json was not uploaded")

        mark_succeeded(job_id, task_arn=task_arn, output_s3_uri=output_uri, summary_s3_uri=summary_uri)
        delete_message(receipt)
        logger.info(json.dumps({"event": "job_succeeded", "job_id": job_id, "task_arn": task_arn}))

    except Exception as exc:
        try:
            mark_failed(
                job_id,
                error_message=str(exc),
                error_type=type(exc).__name__,
                task_arn=task_arn,
            )
        except Exception:
            logger.exception("failed_to_mark_job_failed")
        logger.exception("job_failed")


if __name__ == "__main__":
    main()
