import os
import time
import signal
import logging
from pathlib import Path

from app.infra.sqs_client import receive_message, delete_message
from app.worker.job import set_status, validate_input, validate_output
from app.worker.ecs_runner import run_biomedparse_task

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [worker] %(message)s",
)

shutdown_requested = False


# -----------------------------------------------------------------------------
# Graceful shutdown (ECS sends SIGTERM on task stop)
# -----------------------------------------------------------------------------
def handle_shutdown(signum, frame):
    global shutdown_requested
    logging.info("Shutdown signal received. Finishing current job before exit.")
    shutdown_requested = True


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


# -----------------------------------------------------------------------------
# Job Processing
# -----------------------------------------------------------------------------
def process_one_job(msg: dict):
    job_dir = Path(msg["job_dir"])
    receipt = msg["receipt_handle"]
    job_id = msg["job_id"]

    logging.info(f"Starting job {job_id} in {job_dir}")

    try:
        set_status(job_dir, "running")
        validate_input(job_dir)

        run_biomedparse_task(job_dir)

        validate_output(job_dir)
        set_status(job_dir, "completed")

        delete_message(receipt)
        logging.info(f"Job {job_id} completed successfully and message deleted")

    except Exception:
        logging.exception(f"Job {job_id} failed")
        set_status(job_dir, "failed")
        # Do NOT delete message → SQS will retry
        # Optionally implement DLQ handling later


# -----------------------------------------------------------------------------
# Worker Loop
# -----------------------------------------------------------------------------
def main():
    logging.info("Worker started. Polling SQS for jobs...")

    while not shutdown_requested:
        try:
            msg = receive_message()

            if msg:
                process_one_job(msg)
            else:
                time.sleep(POLL_INTERVAL)

        except Exception:
            # Prevent worker crash from transient AWS/network issues
            logging.exception("Error while polling or processing. Retrying...")
            time.sleep(POLL_INTERVAL)

    logging.info("Worker shutdown complete.")


if __name__ == "__main__":
    main()
