"""
Run this once to create the database schema.

Usage:
    python infra/db_setup.py
"""

import psycopg2
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import POSTGRES_URL


def setup():
    conn = psycopg2.connect(POSTGRES_URL)
    cur = conn.cursor()

    # --- idempotency keys table ---
    # stores processed idempotency keys with expiry
    # this is the durable fallback when Redis loses data
    cur.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            key         TEXT PRIMARY KEY,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            expires_at  TIMESTAMPTZ NOT NULL
        );
    """)

    # --- notifications table ---
    # full audit trail of every notification attempt
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            idempotency_key  TEXT NOT NULL UNIQUE,
            recipient        TEXT NOT NULL,
            channel          TEXT NOT NULL,
            subject          TEXT NOT NULL,
            message          TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'queued',
            -- status: queued | processing | delivered | failed
            attempts         INT NOT NULL DEFAULT 0,
            queued_at        TIMESTAMPTZ DEFAULT NOW(),
            processed_at     TIMESTAMPTZ,
            failed_at        TIMESTAMPTZ,
            error            TEXT
        );
    """)

    # index for fast lookups by recipient (phase 4 — history per user)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_recipient
        ON notifications(recipient);
    """)

    # index for fast status queries
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_status
        ON notifications(status);
    """)

    conn.commit()
    cur.close()
    conn.close()

    print("database schema created.")
    print("  tables: idempotency_keys, notifications")
    print("  indexes: recipient, status")


if __name__ == "__main__":
    setup()