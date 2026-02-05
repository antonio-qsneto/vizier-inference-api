import time
from threading import Thread, Semaphore
from services.sqs import receive_message, delete_message
from services.jobs import write_status, validate_output
from services.ecs import run_biomedparse_task, wait_for_task

def main():
    print("Vizier worker started")
    max_concurrency = int(__import__("os").getenv("WORKER_CONCURRENCY", "2"))
    sem = Semaphore(max_concurrency)

    def _handle(msg):
        try:
            process_one(msg)
        finally:
            sem.release()

    while True:
        # respect concurrency limit
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
    job_dir = msg["job_dir"]
    receipt = msg["receipt_handle"]

    try:
        print(f"[worker] job {job_id} → running")
        write_status(job_dir, "running")

        task_arn = run_biomedparse_task(job_id)
        wait_for_task(task_arn)

        if not validate_output(job_dir):
            raise RuntimeError("pred_mask.npz not found")

        write_status(job_dir, "completed")
        delete_message(receipt)

        print(f"[worker] job {job_id} → completed")

    except Exception as e:
        write_status(job_dir, "failed")
        print(f"[worker] job {job_id} → failed: {e}")

if __name__ == "__main__":
    main()
