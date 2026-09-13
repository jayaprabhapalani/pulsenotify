from pydantic import BaseModel
from enum import Enum
from typing import Optional
import uuid


class Channel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class NotificationRequest(BaseModel):
    recipient: str                        # email / phone / device token
    channel: Channel
    subject: str
    message: str
    idempotency_key: Optional[str] = None # client provides this to prevent duplicates

    def with_defaults(self) -> "NotificationRequest":
        if not self.idempotency_key:
            self.idempotency_key = str(uuid.uuid4())
        return self