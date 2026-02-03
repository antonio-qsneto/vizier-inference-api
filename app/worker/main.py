import time
from services.sqs import receive_message, delete_message
from services.jobs import write_status, validate_output
from services.ecs import run_biomedparse_task, wait_for_task

def main():
    print("Vizier worker started")

    while True:
        msg = receive_message()
        if not msg:
            time.sleep(1)
            continue

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

        time.sleep(1)

if __name__ == "__main__":
    main()
