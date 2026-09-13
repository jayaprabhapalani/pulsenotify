# PulseNotify

async notification platform — built for learning system design concepts hands-on.

## phase 1: SQS + FastAPI worker

**concepts:** async decoupling, visibility timeout, long polling, DLQ, retry

---

## how to run

### 1. start floci (local AWS)

```bash
docker compose up -d
```

### 2. install dependencies

```bash
pip install -r requirements.txt
```

### 3. create SQS queues on floci

```bash
python infra/setup.py
```

you should see:

```
creating DLQ: pulsenotify-dlq
  DLQ URL: http://localhost:4566/000000000000/pulsenotify-dlq
creating main queue: pulsenotify-queue
  Queue URL: http://localhost:4566/000000000000/pulsenotify-queue
setup complete.
```

### 4. start the worker (terminal 1)

```bash
python worker/consumer.py
```

### 5. start the API (terminal 2)

```bash
uvicorn api.main:app --reload
```

### 6. send a notification

```bash
curl -X POST http://localhost:8000/api/v1/notify \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "prabha@example.com",
    "channel": "email",
    "subject": "hello from PulseNotify",
    "message": "phase 1 is working"
  }'
```

**API returns immediately:**

```json
{
  "status": "queued",
  "message_id": "abc-123",
  "idempotency_key": "some-uuid"
}
```

**worker picks it up and logs:**

```
processing notification:
  recipient      : prabha@example.com
  channel        : email
  subject        : hello from PulseNotify
  message        : phase 1 is working
  idempotency_key: some-uuid
notification processed successfully
message deleted: abc-123
```

---

## what to observe

- API returns **before** worker processes the message → async
- kill the worker mid-processing → message reappears after 30s → retry
- send a malformed message → after 3 failures → check DLQ

## verify queues via AWS CLI

```bash
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test

# list queues
aws sqs list-queues

# check message count
aws sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/pulsenotify-queue \
  --attribute-names ApproximateNumberOfMessages
```
