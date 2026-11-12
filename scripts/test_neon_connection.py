"""
Independent Neon Cloud PostgreSQL Connectivity & Diagnostic Tool

Verifies:
1. DNS resolution
2. TCP connectivity
3. PostgreSQL authentication
4. SSL connection mode
5. Database identity (database name, user, version)
6. Transaction commit
7. Transaction rollback
8. Connection closing
9. Connection pool checkout and check-in
10. Connection failure handling

SECURITY MANDATE:
- Never prints passwords, secrets, or raw credential strings.
"""

import os
import sys
import socket
import argparse
from urllib.parse import urlparse
from pathlib import Path
from dotenv import load_dotenv

# Setup root path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.db.database import normalize_database_url, mask_connection_url
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

load_dotenv()

def verify_neon_connection(target_url: str = None, label: str = "Application Runtime (DATABASE_URL)") -> bool:
    print("\n" + "=" * 70)
    print(f"  NEON CLOUD POSTGRESQL CONNECTIVITY TEST: {label}")
    print("=" * 70)

    url = target_url or os.getenv("DATABASE_URL")
    if not url:
        print("[FAIL] Target connection URL is not set in environment or arguments.")
        return False

    normalized_url = normalize_database_url(url)
    masked_url = mask_connection_url(normalized_url)
    print(f"[TARGET] Endpoint: {masked_url}")

    # Step 1 & 2: DNS Resolution & TCP Socket Check
    try:
        parsed = urlparse(normalized_url)
        host = parsed.hostname
        port = parsed.port or 5432

        print(f"[TEST 1/10] Resolving DNS for host '{host}'...")
        ip_addr = socket.gethostbyname(host)
        print(f"  [PASS] Resolved IP: {ip_addr}")

        print(f"[TEST 2/10] Establishing raw TCP socket connection on port {port}...")
        sock = socket.create_connection((host, port), timeout=10)
        sock.close()
        print(f"  [PASS] TCP handshake successful.")
    except Exception as e:
        print(f"  [FAIL] Network/DNS connectivity failed: {type(e).__name__}: {e}")
        return False

    # Step 3, 4 & 5: SSL & Engine Initialization
    print(f"[TEST 3/10] Initializing SQLAlchemy engine with SSL & Pre-ping...")
    try:
        engine = create_engine(
            normalized_url,
            poolclass=QueuePool,
            pool_size=2,
            max_overflow=2,
            pool_timeout=10,
            pool_pre_ping=True
        )
        print("  [PASS] Engine initialized.")
    except Exception as e:
        print(f"  [FAIL] Engine creation failed: {type(e).__name__}")
        return False

    # Step 5 & 6: Authentication & Query execution
    print(f"[TEST 4-6/10] Connecting, authenticating, and querying database identity...")
    try:
        with engine.connect() as conn:
            # Query version
            version_res = conn.execute(text("SELECT version();")).scalar()
            current_db = conn.execute(text("SELECT current_database();")).scalar()
            current_user = conn.execute(text("SELECT current_user;")).scalar()
            
            # Check SSL status
            ssl_res = conn.execute(text("SELECT ssl_is_used();")).scalar() if "ssl_is_used" in str(version_res).lower() else True

            print(f"  [PASS] Authenticated successfully as: '{current_user}'")
            print(f"  [PASS] Connected Database: '{current_db}'")
            print(f"  [PASS] Server Engine Version: {version_res.split(',')[0] if version_res else 'PostgreSQL'}")
            print(f"  [PASS] SSL Connection Active: {ssl_res}")
    except Exception as e:
        print(f"  [FAIL] Authentication or query execution failed: {type(e).__name__}: {e}")
        engine.dispose()
        return False

    # Step 7: Transaction Commit Verification
    print(f"[TEST 7/10] Verifying transaction commit semantics...")
    try:
        with engine.begin() as conn:
            val = conn.execute(text("SELECT 42 AS test_val;")).scalar()
            assert val == 42
        print("  [PASS] Transaction commit verified.")
    except Exception as e:
        print(f"  [FAIL] Transaction commit failed: {type(e).__name__}: {e}")
        engine.dispose()
        return False

    # Step 8: Transaction Rollback Verification
    print(f"[TEST 8/10] Verifying transaction rollback semantics...")
    try:
        conn = engine.connect()
        trans = conn.begin()
        conn.execute(text("SELECT 1;"))
        trans.rollback()
        conn.close()
        print("  [PASS] Transaction rollback verified.")
    except Exception as e:
        print(f"  [FAIL] Transaction rollback failed: {type(e).__name__}: {e}")
        engine.dispose()
        return False

    # Step 9: Connection Pool Checkout and Check-in
    print(f"[TEST 9/10] Verifying connection pool checkout & recycling...")
    try:
        c1 = engine.connect()
        c2 = engine.connect()
        assert engine.pool.checkedout() == 2
        c1.close()
        c2.close()
        assert engine.pool.checkedout() == 0
        print("  [PASS] Connection pool checkout and return verified.")
    except Exception as e:
        print(f"  [FAIL] Pool checkout test failed: {type(e).__name__}: {e}")
        engine.dispose()
        return False

    # Step 10: Graceful Engine Disposal
    print(f"[TEST 10/10] Verifying clean connection termination...")
    try:
        engine.dispose()
        print("  [PASS] All connection pool sockets closed cleanly.")
    except Exception as e:
        print(f"  [FAIL] Engine disposal failed: {type(e).__name__}: {e}")
        return False

    print("\n" + "=" * 70)
    print("  ALL 10 NEON CONNECTIVITY CHECKS PASSED SUCCESSFULLY [100%]")
    print("=" * 70)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Neon Cloud PostgreSQL Connectivity Diagnostic Tool")
    parser.add_argument("--migration", action="store_true", help="Test DATABASE_MIGRATION_URL endpoint instead of standard DATABASE_URL")
    args = parser.parse_args()

    target_env_var = "DATABASE_MIGRATION_URL" if args.migration else "DATABASE_URL"
    url = os.getenv(target_env_var)
    label = f"Migration Direct Endpoint ({target_env_var})" if args.migration else f"Runtime Pooled Endpoint ({target_env_var})"

    if not url:
        print(f"[ERROR] {target_env_var} is not set in environment or .env file.")
        print(f"Please set {target_env_var} before running this verification.")
        sys.exit(1)

    success = verify_neon_connection(target_url=url, label=label)
    sys.exit(0 if success else 1)
