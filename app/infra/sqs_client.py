import os
import json
import boto3

def get_sqs():
    region = os.getenv("AWS_REGION", "us-east-1")
    return boto3.client("sqs", region_name=region)

def get_queue_url():
    url = os.getenv("SQS_QUEUE_URL")
    if not url:
        raise RuntimeError("SQS_QUEUE_URL environment variable is not set")
    return url

def enqueue_job(job_id: str, job_dir: str):
    sqs = get_sqs()
    sqs.send_message(
        QueueUrl=get_queue_url(),
        MessageBody=json.dumps({"job_id": job_id, "job_dir": job_dir}),
    )

def receive_message(wait_seconds=20):
    sqs = get_sqs()
    resp = sqs.receive_message(
        QueueUrl=get_queue_url(),
        MaxNumberOfMessages=1,
        WaitTimeSeconds=wait_seconds,
    )
    msgs = resp.get("Messages", [])
    if not msgs:
        return None

    msg = msgs[0]
    body = json.loads(msg["Body"])
    return {
        "receipt_handle": msg["ReceiptHandle"],
        "job_id": body["job_id"],
        "job_dir": body["job_dir"],
    }

def delete_message(receipt_handle: str):
    sqs = get_sqs()
    sqs.delete_message(
        QueueUrl=get_queue_url(),
        ReceiptHandle=receipt_handle,
    )
