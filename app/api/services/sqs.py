import json

import boto3

from settings import settings

sqs = boto3.client(
    "sqs",
    region_name=settings.AWS_REGION,
)


def enqueue_job(message: dict) -> None:
    sqs.send_message(
        QueueUrl=settings.SQS_QUEUE_URL,
        MessageBody=json.dumps(message),
    )
