"""
Script to reset stuck processing documents and jobs in the database.
Run this locally or via Render shell to fix stuck pipeline jobs.

Usage:
    python scripts/reset_stuck_jobs.py

Requirements:
    - DATABASE_URL env var must be set (or .env file present)
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

# Fix asyncpg URL for sync use
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # 1. Count stuck documents
    stuck_docs = conn.execute(text("SELECT COUNT(*) FROM documents WHERE status = 'processing'")).scalar()
    print(f"Found {stuck_docs} documents stuck at 'processing'")

    # 2. Reset stuck documents to 'failed' (so they can be re-uploaded)
    result = conn.execute(text(
        "UPDATE documents SET status = 'failed' WHERE status = 'processing'"
    ))
    conn.commit()
    print(f"Reset {result.rowcount} documents to 'failed' status")

    # 3. Count stuck jobs
    stuck_jobs = conn.execute(text(
        "SELECT COUNT(*) FROM ingestion_jobs WHERE status IN ('processing', 'pending') AND created_at < NOW() - INTERVAL '30 minutes'"
    )).scalar()
    print(f"Found {stuck_jobs} stale pipeline jobs")

    # 4. Reset stale jobs older than 30 minutes
    result = conn.execute(text(
        "UPDATE ingestion_jobs SET status = 'failed', error_message = 'Reset by admin: stuck job cleanup' "
        "WHERE status IN ('processing', 'pending') AND created_at < NOW() - INTERVAL '30 minutes'"
    ))
    conn.commit()
    print(f"Reset {result.rowcount} stale jobs to 'failed' status")

    # 5. Show current state
    print("\n=== Current Database State ===")
    docs = conn.execute(text("SELECT status, COUNT(*) as count FROM documents GROUP BY status")).fetchall()
    for row in docs:
        print(f"  Documents [{row[0]}]: {row[1]}")

    jobs = conn.execute(text("SELECT status, COUNT(*) as count FROM ingestion_jobs GROUP BY status")).fetchall()
    for row in jobs:
        print(f"  Jobs [{row[0]}]: {row[1]}")

print("\nDone! Re-upload your documents to re-index them.")
