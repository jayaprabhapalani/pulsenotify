"""
SQS consumer — run this as a separate process alongside the API.

Usage:
    python worker/consumer.py

This worker:
1. long-polls SQS for messages (waits up to 20s if queue is empty)
2. processes each message
3. explicitly deletes it from SQS on success
4. if processing fails, does NOT delete → message becomes visible again after
   visibility timeout → retried → after MAX_RECEIVE_COUNT failures → goes to DLQ
"""

import boto3
import json
import time
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import (
    AWS_ENDPOINT_URL, AWS_REGION,
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    QUEUE_NAME, LONG_POLL_WAIT_TIME
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def get_sqs_client():
    return boto3.client(
        "sqs",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def process_message(body: dict) -> None:
    """
    This is where actual notification delivery would happen.
    For phase 1 — we just log it.
    Phase 4 — this will call SNS/SES.
    """
    log.info(f"processing notification:")
    log.info(f"  recipient      : {body['recipient']}")
    log.info(f"  channel        : {body['channel']}")
    log.info(f"  subject        : {body['subject']}")
    log.info(f"  message        : {body['message']}")
    log.info(f"  idempotency_key: {body['idempotency_key']}")

    # simulate processing time
    time.sleep(0.5)
    log.info("notification processed successfully")
    #raise Exception("simulated failure") - to simulate visibility timedout -max retries - then msg moves- to dlq

def run():
    sqs = get_sqs_client()
    queue_url = sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]

    log.info(f"worker started. polling queue: {QUEUE_NAME}")
    log.info(f"long poll wait time: {LONG_POLL_WAIT_TIME}s")

    while True:
        # long polling — blocks up to LONG_POLL_WAIT_TIME seconds if queue is empty
        # much more efficient than short polling (which returns immediately even when empty)
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,          # process up to 10 at a time
            WaitTimeSeconds=LONG_POLL_WAIT_TIME,
            MessageAttributeNames=["All"],   # fetch metadata too
        )

        messages = response.get("Messages", [])

        if not messages:
            log.debug("queue empty, waiting...")
            continue

        log.info(f"received {len(messages)} message(s)")

        for msg in messages:
            receipt_handle = msg["ReceiptHandle"]  # needed to delete the message
            approximate_receive_count = msg.get("Attributes", {}).get("ApproximateReceiveCount", "?")

            log.info(f"processing message (attempt #{approximate_receive_count}): {msg['MessageId']}")

            try:
                body = json.loads(msg["Body"])
                process_message(body)

                # SUCCESS — delete the message so it doesn't get reprocessed
                # this is the explicit acknowledgment SQS requires
                sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt_handle
                )
                log.info(f"message deleted: {msg['MessageId']}")

            except Exception as e:
                # FAILURE — do NOT delete
                # message stays hidden until visibility timeout expires
                # then becomes visible again for retry
                # after MAX_RECEIVE_COUNT failures → moves to DLQ
                log.error(f"failed to process message {msg['MessageId']}: {e}")
                log.error(f"message will be retried after visibility timeout")


if __name__ == "__main__":
    run()