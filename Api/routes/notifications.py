import boto3
import json
from fastapi import APIRouter, HTTPException
from models.notification import NotificationRequest
from config import (
    AWS_ENDPOINT_URL, AWS_REGION,
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    QUEUE_NAME
)

router = APIRouter()

# boto3 SQS client — reused across requests
sqs = boto3.client(
    "sqs",
    endpoint_url=AWS_ENDPOINT_URL,
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)


def get_queue_url() -> str:
    response = sqs.get_queue_url(QueueName=QUEUE_NAME)
    return response["QueueUrl"]


@router.post("/notify")
async def send_notification(request: NotificationRequest):
    """
    Accepts a notification request and puts it on SQS.
    Returns immediately — does NOT wait for the message to be processed.
    This is the core of async decoupling.
    """
    request = request.with_defaults()

    try:
        queue_url = get_queue_url()

        # serialize the notification to JSON and publish to SQS
        # MessageDeduplicationId is for FIFO queues — we'll cover that later
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(request.model_dump()),
            # MessageAttributes let you attach metadata without touching the body
            # useful for routing, filtering — we'll use this in phase 4 with SNS
            MessageAttributes={
                "channel": {
                    "DataType": "String",
                    "StringValue": request.channel.value,
                },
                "idempotency_key": {
                    "DataType": "String",
                    "StringValue": request.idempotency_key,
                }
            }
        )

        return {
            "status": "queued",
            "message_id": response["MessageId"],
            "idempotency_key": request.idempotency_key,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))