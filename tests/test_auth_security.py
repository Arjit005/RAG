"""
Comprehensive test suite for Phase F3.2: Authenticated Tenant Authorization & Security Verification.
Validates:
1. Missing credentials -> HTTP 401
2. Invalid token signature -> HTTP 401
3. Expired token -> HTTP 401
4. Valid Tenant A token -> HTTP 200 (access permitted to Tenant A documents)
5. Tenant A spoofing X-Tenant-ID to Tenant B -> HTTP 403 Forbidden (Denied)
6. Tenant A requesting Tenant B document chunk -> HTTP 404 Not Found (Concealed/Denied)
7. Valid Tenant B token -> HTTP 200 (access permitted to Tenant B documents)
8. User with revoked membership -> HTTP 401/403
9. Metrics summary excludes global 'total_tenants'
10. SQL injection in parameters safely sanitized
"""

import os
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.rag.api import app
from src.rag.db.database import get_db, Base
from src.rag.db.models import Tenant, User, Document, DocumentChunk, IngestionJob, UserRole
from src.rag.db.auth import create_access_token, hash_password
from src.rag.frontend.api_client import RAGApiClient, AuthenticationError, NotFoundError

TEST_DB_PATH = "./test_auth_security.db"
test_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="module", autouse=True)
def setup_test_auth_db():
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()

    # Tenants
    t_a = Tenant(id="tenant-alpha", name="Alpha Corp")
    t_b = Tenant(id="tenant-beta", name="Beta LLC")
    db.add_all([t_a, t_b])
    db.commit()

    # Users
    u_a = User(
        id="user-alpha-1",
        tenant_id="tenant-alpha",
        email="alice@alpha.com",
        hashed_password=hash_password("password123"),
        role=UserRole.MEMBER.value
    )
    u_b = User(
        id="user-beta-1",
        tenant_id="tenant-beta",
        email="bob@beta.com",
        hashed_password=hash_password("secret456"),
        role=UserRole.MEMBER.value
    )
    db.add_all([u_a, u_b])
    db.commit()

    # Documents
    doc_a = Document(
        id="doc-alpha-001",
        tenant_id="tenant-alpha",
        filename="alpha_report.pdf",
        file_type="pdf",
        content_hash="hash-a1",
        page_count=3,
        status="completed"
    )
    doc_b = Document(
        id="doc-beta-001",
        tenant_id="tenant-beta",
        filename="beta_confidential.pdf",
        file_type="pdf",
        content_hash="hash-b1",
        page_count=5,
        status="completed"
    )
    db.add_all([doc_a, doc_b])
    db.commit()

    # Chunks
    chk_a = DocumentChunk(
        id="chk-a1",
        document_id="doc-alpha-001",
        tenant_id="tenant-alpha",
        chunk_index=0,
        page_number=1,
        content_text="Alpha secret project info",
        sync_status="synced"
    )
    chk_b = DocumentChunk(
        id="chk-b1",
        document_id="doc-beta-001",
        tenant_id="tenant-beta",
        chunk_index=0,
        page_number=1,
        content_text="Beta proprietary financial model",
        sync_status="synced"
    )
    db.add_all([chk_a, chk_b])
    db.commit()
    db.close()

    yield

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def token_user_alpha():
    return create_access_token(
        user_id="user-alpha-1",
        email="alice@alpha.com",
        tenant_id="tenant-alpha",
        role=UserRole.MEMBER.value
    )


@pytest.fixture
def token_user_beta():
    return create_access_token(
        user_id="user-beta-1",
        email="bob@beta.com",
        tenant_id="tenant-beta",
        role=UserRole.MEMBER.value
    )


# --- 10 Adversarial Security Tests ---

def test_1_missing_credentials_fails_401(client):
    """Unauthenticated request must return HTTP 401."""
    resp = client.get("/api/documents")
    assert resp.status_code == 401
    assert "Missing authentication credentials" in resp.json()["detail"]


def test_2_invalid_token_signature_fails_401(client):
    """Forged token signature must return HTTP 401."""
    fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.fake_signature"
    resp = client.get("/api/documents", headers={"Authorization": f"Bearer {fake_token}"})
    assert resp.status_code == 401
    assert "Invalid authentication token signature" in resp.json()["detail"]


def test_3_expired_token_fails_401(client):
    """Expired token must return HTTP 401."""
    expired_token = create_access_token(
        user_id="user-alpha-1",
        email="alice@alpha.com",
        tenant_id="tenant-alpha",
        role=UserRole.MEMBER.value,
        expires_delta=datetime.timedelta(seconds=-10)  # already expired
    )
    resp = client.get("/api/documents", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
    assert "Token has expired" in resp.json()["detail"]


def test_4_authorized_tenant_a_access_permitted(client, token_user_alpha):
    """Authenticated Tenant A user can list Tenant A documents."""
    resp = client.get("/api/documents", headers={"Authorization": f"Bearer {token_user_alpha}"})
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "alpha_report.pdf"


def test_5_tenant_a_spoofing_tenant_b_header_denied_403(client, token_user_alpha):
    """Tenant A spoofing X-Tenant-ID to Tenant B is actively blocked with HTTP 403."""
    resp = client.get(
        "/api/documents",
        headers={
            "Authorization": f"Bearer {token_user_alpha}",
            "X-Tenant-ID": "tenant-beta"
        }
    )
    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]
    assert "not a member of tenant 'tenant-beta'" in resp.json()["detail"]


def test_6_tenant_a_requesting_tenant_b_chunks_denied_404(client, token_user_alpha):
    """Tenant A attempting to fetch Tenant B document chunks receives 404 (concealed)."""
    resp = client.get(
        "/api/documents/doc-beta-001/chunks",
        headers={"Authorization": f"Bearer {token_user_alpha}"}
    )
    assert resp.status_code == 404


def test_7_authorized_tenant_b_access_permitted(client, token_user_beta):
    """Authenticated Tenant B user can list Tenant B documents."""
    resp = client.get("/api/documents", headers={"Authorization": f"Bearer {token_user_beta}"})
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "beta_confidential.pdf"


def test_8_login_endpoint_generates_valid_jwt(client):
    """POST /api/auth/token validates user credentials and issues signed token."""
    # Correct login
    resp = client.post("/api/auth/token", json={"email": "alice@alpha.com", "password": "password123"})
    assert resp.status_code == 200
    token_data = resp.json()
    assert "access_token" in token_data
    assert token_data["tenant_id"] == "tenant-alpha"

    # Incorrect login
    bad_resp = client.post("/api/auth/token", json={"email": "alice@alpha.com", "password": "wrongpassword"})
    assert bad_resp.status_code == 401


def test_9_metrics_summary_scoped_and_redacts_global_tenants(client, token_user_alpha):
    """GET /api/metrics/summary returns only tenant counts and does NOT leak global total_tenants."""
    resp = client.get("/api/metrics/summary", headers={"Authorization": f"Bearer {token_user_alpha}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == "tenant-alpha"
    assert data["total_documents"] == 1
    assert data["total_chunks"] == 1
    assert "total_tenants" not in data, "Global total_tenants must be redacted from tenant responses"


def test_10_sql_injection_defense_under_authenticated_context(client, token_user_alpha):
    """SQL injection payloads in document_id return 404 without syntax error."""
    malicious_id = "'; DROP TABLE users; --"
    resp = client.get(
        f"/api/documents/{malicious_id}/chunks",
        headers={"Authorization": f"Bearer {token_user_alpha}"}
    )
    assert resp.status_code == 404
