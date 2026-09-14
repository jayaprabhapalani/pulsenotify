"""
Sliding window rate limiter using Redis sorted sets.

How it works:
- each unique key (sender or recipient) has a sorted set in Redis
- sorted set members = request IDs, scores = timestamps (unix ms)
- on each request:
    1. remove entries older than the window
    2. count remaining entries
    3. if count >= limit → reject (429)
    4. else → add current request with current timestamp → allow
- TTL is set on the key so it auto-expires when inactive

Why sorted sets?
- score-based range queries let us remove old entries in O(log N)
- atomic via Lua script → no race conditions under concurrent requests
"""

import time
import uuid
import redis
from dataclasses import dataclass
from config import REDIS_URL


@dataclass
class RateLimitConfig:
    limit: int        # max requests allowed
    window_ms: int    # time window in milliseconds


# rate limit rules
#SENDER_LIMIT = RateLimitConfig(limit=100, window_ms=60_000)
SENDER_LIMIT = RateLimitConfig(limit=3, window_ms=60_000)# 3 req/min for testing        # 100 req/min per sender
RECIPIENT_LIMIT = RateLimitConfig(limit=10, window_ms=3_600_000)  # 10 notifications/hour per recipient


# Lua script for atomic sliding window check + insert
# runs as a single atomic operation in Redis — no race conditions
SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local request_id = ARGV[4]
local window_start = now - window_ms

-- step 1: remove entries older than window
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

-- step 2: count current entries in window
local count = redis.call('ZCARD', key)

-- step 3: check limit
if count >= limit then
    return 0  -- rejected
end

-- step 4: add current request
redis.call('ZADD', key, now, request_id)

-- set TTL so key auto-expires when inactive (window_ms + 1s buffer, in seconds)
redis.call('PEXPIRE', key, window_ms + 1000)

return 1  -- allowed
"""


class RateLimiter:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        # register the Lua script — returns a callable
        self._script = self.redis.register_script(SLIDING_WINDOW_SCRIPT)

    def _check(self, key: str, config: RateLimitConfig) -> bool:
        """
        Returns True if request is allowed, False if rate limited.
        """
        now_ms = int(time.time() * 1000)
        request_id = str(uuid.uuid4())

        result = self._script(
            keys=[key],
            args=[now_ms, config.window_ms, config.limit, request_id]
        )
        return bool(result)

    def check_sender(self, api_key: str) -> bool:
        key = f"rate_limit:sender:{api_key}"
        return self._check(key, SENDER_LIMIT)

    def check_recipient(self, recipient: str) -> bool:
        key = f"rate_limit:recipient:{recipient}"
        return self._check(key, RECIPIENT_LIMIT)

    def get_usage(self, key_type: str, identifier: str) -> dict:
        """
        Returns current usage for a key — useful for debugging and headers.
        """
        if key_type == "sender":
            key = f"rate_limit:sender:{identifier}"
            config = SENDER_LIMIT
        else:
            key = f"rate_limit:recipient:{identifier}"
            config = RECIPIENT_LIMIT

        now_ms = int(time.time() * 1000)
        window_start = now_ms - config.window_ms

        # clean old entries first
        self.redis.zremrangebyscore(key, '-inf', window_start)
        count = self.redis.zcard(key)

        return {
            "current": count,
            "limit": config.limit,
            "remaining": max(0, config.limit - count),
            "window_ms": config.window_ms,
        }


# singleton — one instance shared across the app
rate_limiter = RateLimiter()

