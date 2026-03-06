import json

import boto3

from settings import settings

_sqs = boto3.client("sqs", region_name=settings.AWS_REGION)


def receive_message():
    resp = _sqs.receive_message(
        QueueUrl=settings.SQS_QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=settings.SQS_WAIT_SECONDS,
        AttributeNames=["ApproximateReceiveCount"],
    )

    msgs = resp.get("Messages", [])
    if not msgs:
        return None

    msg = msgs[0]
    body = json.loads(msg["Body"])

    return {
        "receipt_handle": msg["ReceiptHandle"],
        "receive_count": int(msg.get("Attributes", {}).get("ApproximateReceiveCount", "1")),
        **body,
    }


def delete_message(receipt_handle: str):
    _sqs.delete_message(
        QueueUrl=settings.SQS_QUEUE_URL,
        ReceiptHandle=receipt_handle,
    )


def change_message_visibility(receipt_handle: str, timeout_seconds: int):
    _sqs.change_message_visibility(
        QueueUrl=settings.SQS_QUEUE_URL,
        ReceiptHandle=receipt_handle,
        VisibilityTimeout=timeout_seconds,
    )
