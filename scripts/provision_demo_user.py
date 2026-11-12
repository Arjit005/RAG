"""
CLI script to idempotently ensure the existence of the portfolio demo account.
Reads credentials securely from environment variables:
- DEMO_USER_EMAIL (default: admin@enterprise.internal)
- DEMO_USER_PASSWORD (default: EnterpriseAdmin2026!)
- DEMO_TENANT_ID (default: default-tenant)
- DEMO_USER_ROLE (default: system_admin)
"""

import os
import sys
import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.db.database import SessionLocal
from src.rag.db.models import User, Tenant, UserRole
from src.rag.db.auth import hash_password, verify_password


def provision_demo_account():
    email = os.getenv("DEMO_USER_EMAIL", "admin@enterprise.internal").strip()
    password = os.getenv("DEMO_USER_PASSWORD", "EnterpriseAdmin2026!").strip()
    tenant_id = os.getenv("DEMO_TENANT_ID", "default-tenant").strip()
    role = os.getenv("DEMO_USER_ROLE", UserRole.SYSTEM_ADMIN.value).strip()

    if not email or not password:
        print("[ERROR] DEMO_USER_EMAIL and DEMO_USER_PASSWORD cannot be empty.")
        sys.exit(1)

    db = SessionLocal()
    try:
        # 1. Verify or ensure demo tenant exists
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            print(f"[INFO] Provisioning default demo tenant: '{tenant_id}'")
            tenant = Tenant(
                id=tenant_id,
                name="Default Enterprise Org",
                created_at=datetime.datetime.utcnow(),
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        # 2. Check if demo user already exists
        user = db.query(User).filter(User.email == email).first()
        if user:
            # Check if existing password matches
            if user.hashed_password and verify_password(password, user.hashed_password):
                print(f"[OK] Demo user '{email}' already exists and credentials are verified.")
            else:
                # Update password idempotently if requested by explicit env or creation
                print(f"[NOTICE] Updating password for existing demo user '{email}'.")
                user.hashed_password = hash_password(password)
                user.role = role
                user.tenant_id = tenant_id
                db.commit()
                print(f"[OK] Password updated for demo user '{email}'.")
        else:
            print(f"[INFO] Creating demo user '{email}'...")
            new_user = User(
                id="user-admin-default",
                tenant_id=tenant_id,
                email=email,
                hashed_password=hash_password(password),
                role=role,
                created_at=datetime.datetime.utcnow(),
            )
            db.add(new_user)
            db.commit()
            print(f"[OK] Successfully provisioned demo user '{email}'.")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to provision demo account: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    provision_demo_account()
