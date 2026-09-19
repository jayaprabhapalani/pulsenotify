"""
Notification repository.
All database operations for the notifications table.
"""

import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from typing import Optional
from config import POSTGRES_URL


class NotificationRepository:
    def _conn(self):
        return psycopg2.connect(POSTGRES_URL)

    def create(self, notification: dict) -> None:
        """
        Insert a new notification record when it's queued.
        Status starts as 'queued'.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO notifications (
                    idempotency_key, recipient, channel,
                    subject, message, status
                ) VALUES (%s, %s, %s, %s, %s, 'queued')
                ON CONFLICT (idempotency_key) DO NOTHING
            """, (
                notification["idempotency_key"],
                notification["recipient"],
                notification["channel"],
                notification["subject"],
                notification["message"],
            ))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def mark_processing(self, idempotency_key: str) -> None:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE notifications
                SET status = 'processing', attempts = attempts + 1
                WHERE idempotency_key = %s
            """, (idempotency_key,))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def mark_delivered(self, idempotency_key: str) -> None:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE notifications
                SET status = 'delivered', processed_at = NOW()
                WHERE idempotency_key = %s
            """, (idempotency_key,))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def mark_failed(self, idempotency_key: str, error: str) -> None:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE notifications
                SET status = 'failed', failed_at = NOW(), error = %s
                WHERE idempotency_key = %s
            """, (error, idempotency_key))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def get_by_recipient(self, recipient: str) -> list:
        conn = self._conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM notifications
                WHERE recipient = %s
                ORDER BY queued_at DESC
                LIMIT 50
            """, (recipient,))
            return [dict(row) for row in cur.fetchall()]
        finally:
            cur.close()
            conn.close()


# singleton
notification_repo = NotificationRepository()