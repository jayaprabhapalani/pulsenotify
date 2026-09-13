"""
Run this once before starting the app.
Creates the SQS queue and DLQ on floci.

Usage:
    python infra/setup.py
"""

import boto3
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import (
    AWS_ENDPOINT_URL, AWS_REGION,
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    QUEUE_NAME, DLQ_NAME,
    VISIBILITY_TIMEOUT, MAX_RECEIVE_COUNT
)


def get_sqs_client():
    return boto3.client(
        "sqs",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def setup():
    sqs = get_sqs_client()

    # --- step 1: create DLQ first ---
    # DLQ is just a normal SQS queue. we create it first
    # because the main queue needs its ARN to configure redrive policy.
    print(f"creating DLQ: {DLQ_NAME}")
    dlq_response = sqs.create_queue(
        QueueName=DLQ_NAME,
        Attributes={
            "MessageRetentionPeriod": "1209600",  # 14 days in seconds
        }
    )
    dlq_url = dlq_response["QueueUrl"]
    print(f"  DLQ URL: {dlq_url}")

    # get DLQ ARN — needed for redrive policy
    dlq_attrs = sqs.get_queue_attributes(
        QueueUrl=dlq_url,
        AttributeNames=["QueueArn"]
    )
    dlq_arn = dlq_attrs["Attributes"]["QueueArn"]
    print(f"  DLQ ARN: {dlq_arn}")

    # --- step 2: create main queue with redrive policy ---
    # redrive policy tells SQS:
    # "after MAX_RECEIVE_COUNT failed attempts, move message to DLQ"
    print(f"\ncreating main queue: {QUEUE_NAME}")
    queue_response = sqs.create_queue(
        QueueName=QUEUE_NAME,
        Attributes={
            "VisibilityTimeout": str(VISIBILITY_TIMEOUT),
            "MessageRetentionPeriod": "86400",   # 1 day
            "ReceiveMessageWaitTimeSeconds": "20", # enables long polling by default
            "RedrivePolicy": json.dumps({
                "deadLetterTargetArn": dlq_arn,
                "maxReceiveCount": str(MAX_RECEIVE_COUNT),
            }),
        }
    )
    queue_url = queue_response["QueueUrl"]
    print(f"  Queue URL: {queue_url}")

    print("\nsetup complete. queues ready.")
    print(f"  main queue : {queue_url}")
    print(f"  DLQ        : {dlq_url}")


if __name__ == "__main__":
    setup()