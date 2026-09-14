import boto3
import json
from fastapi import APIRouter, HTTPException,Header
from typing import Optional
from models.notification import NotificationRequest
from worker.rate_limiter import rate_limiter
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
async def send_notification(
    request: NotificationRequest,
    x_api_key: Optional[str] = Header(default="default-sender")  # sender identification):
):
    """
    Accepts a notification request and puts it on SQS.
    Returns immediately — does NOT wait for the message to be processed.
    This is the core of async decoupling.
    
    Rate limited by:
    - sender (api key): 100 req/min
    - recipient: 10 notifications/hour
    """
    request = request.with_defaults()
    
     # --- rate limit check: sender ---
    if not rate_limiter.check_sender(x_api_key):
        usage = rate_limiter.get_usage("sender", x_api_key)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "sender rate limit exceeded",
                "limit": usage["limit"],
                "window": "1 minute",
                "retry_after": "60s",
            }
        )
     # --- rate limit check: recipient ---
    if not rate_limiter.check_recipient(request.recipient):
        usage = rate_limiter.get_usage("recipient", request.recipient)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "recipient rate limit exceeded",
                "limit": usage["limit"],
                "window": "1 hour",
                "retry_after": "3600s",
            }
        )

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