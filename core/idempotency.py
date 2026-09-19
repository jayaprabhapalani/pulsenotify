"""
Idempotency layer.

Two-level check:
1. Redis  — fast, in-memory, TTL-based
2. Postgres — durable fallback if Redis loses data

Write path (after successful processing):
1. write to Postgres first (durable)
2. then backfill Redis (fast path for future checks)

This order matters — if Redis write fails after Postgres write, 
we still have durability. reverse order would lose the record.
"""

import redis
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from config import REDIS_URL, POSTGRES_URL

# how long to remember an idempotency key
# set this to match your business requirement
# 24h means: same key within 24h = duplicate
IDEMPOTENCY_TTL_SECONDS = 86_400  # 24 hours
IDEMPOTENCY_TTL_MS = IDEMPOTENCY_TTL_SECONDS * 1000


class IdempotencyStore:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)

    def _redis_key(self, idempotency_key: str) -> str:
        return f"idempotency:{idempotency_key}"

    def exists(self, idempotency_key: str) -> bool:
        """
        Check if this key was already processed.
        Fast path: Redis. Fallback: Postgres.
        """
        # --- level 1: Redis (microseconds) ---
        redis_key = self._redis_key(idempotency_key)
        if self.redis.exists(redis_key):
            return True

        # --- level 2: Postgres (milliseconds, but durable) ---
        # Redis might have lost data on restart
        conn = psycopg2.connect(POSTGRES_URL)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM idempotency_keys
                WHERE key = %s AND expires_at > NOW()
            """, (idempotency_key,))
            row = cur.fetchone()

            if row:
                # backfill Redis so next check is fast again
                ttl = self.redis.ttl(redis_key)
                if ttl < 0:
                    self.redis.setex(redis_key, IDEMPOTENCY_TTL_SECONDS, "1")
                return True

            return False
        finally:
            cur.close()
            conn.close()

    def mark_processed(self, idempotency_key: str) -> None:
        """
        Mark a key as processed.
        Write to Postgres first (durable), then Redis (fast path).
        """
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=IDEMPOTENCY_TTL_SECONDS)

        # --- write to Postgres first ---
        conn = psycopg2.connect(POSTGRES_URL)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO idempotency_keys (key, expires_at)
                VALUES (%s, %s)
                ON CONFLICT (key) DO NOTHING
            """, (idempotency_key, expires_at))
            conn.commit()
        finally:
            cur.close()
            conn.close()

        # --- then backfill Redis ---
        redis_key = self._redis_key(idempotency_key)
        self.redis.setex(redis_key, IDEMPOTENCY_TTL_SECONDS, "1")


# singleton
idempotency_store = IdempotencyStore()