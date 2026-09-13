import os

# floci runs at localhost:4566 and mimics AWS
# credentials can be any non-empty string — floci doesn't validate them
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "test")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "test")

# SQS
QUEUE_NAME = "pulsenotify-queue"
DLQ_NAME = "pulsenotify-dlq"

# how long a message is hidden from other workers after being picked up
# if worker crashes before deleting the message, it reappears after this
VISIBILITY_TIMEOUT = 30  # seconds

# max times a message can fail before going to DLQ
MAX_RECEIVE_COUNT = 3

# long polling — worker waits up to 20s for a message before returning empty
LONG_POLL_WAIT_TIME = 20  # seconds