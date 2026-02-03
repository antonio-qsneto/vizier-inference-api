# app/api/services/sqs.py  (PRODUCTION)

import json
import boto3
from settings import settings

sqs = boto3.client(
    "sqs",
    region_name=settings.AWS_REGION,
)

def enqueue_job(job_id: str, job_dir: str):
    sqs.send_message(
        QueueUrl=settings.SQS_QUEUE_URL,
        MessageBody=json.dumps({
            "job_id": job_id,
            "job_dir": job_dir,
        }),
    )
