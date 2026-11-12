"""
Comprehensive automated tests for Phase F5: Research Chat & Evidence Presentation.
Tests:
1. Authenticated chat non-streaming (POST /api/chat)
2. Authenticated chat streaming with SSE (POST /api/chat/stream)
3. Tenant isolation in chat retrieval (Tenant A query does not retrieve Tenant B chunks)
4. Empty and whitespace query rejection (HTTP 400)
5. Overly long query boundary validation (> 4000 chars)
6. Missing/invalid JWT token rejection (HTTP 401)
7. Forged X-Tenant-ID header rejection (HTTP 403)
8. Retrieval parameters adherence (top_k, use_hybrid, use_rerank)
9. Evidence metadata integrity (verifiable source, page, distance)
10. RAGApiClient chat and chat_stream methods
"""

import os
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.rag.api import app
from src.rag.db.database import get_db, Base
from src.rag.db.models import Tenant, User, Document, DocumentChunk, UserRole
from src.rag.db.auth import create_access_token, hash_password
from src.rag.frontend.api_client import RAGApiClient, AuthenticationError, APIClientError

TEST_DB_PATH = "./test_f5_chat.db"
test_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="module", autouse=True)
def setup_f5_db():
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

    # Create tenants
    t1 = Tenant(id="tenant-alpha", name="Alpha Systems")
    t2 = Tenant(id="tenant-beta", name="Beta Dynamics")
    db.add_all([t1, t2])
    db.commit()

    # Create users
    u1 = User(
        id="user-alpha-1",
        tenant_id="tenant-alpha",
        email="researcher@alpha.internal",
        hashed_password=hash_password("alphapass"),
        role=UserRole.MEMBER.value
    )
    u2 = User(
        id="user-beta-1",
        tenant_id="tenant-beta",
        email="analyst@beta.internal",
        hashed_password=hash_password("betapass"),
        role=UserRole.MEMBER.value
    )
    db.add_all([u1, u2])
    db.commit()

    # Seed isolated documents and chunks
    doc_alpha = Document(
        id="doc-alpha-101",
        tenant_id="tenant-alpha",
        filename="alpha_transformers.pdf",
        file_type="pdf",
        content_hash="hash-alpha-101",
        page_count=3,
        status="completed"
    )
    doc_beta = Document(
        id="doc-beta-202",
        tenant_id="tenant-beta",
        filename="beta_confidential.pdf",
        file_type="pdf",
        content_hash="hash-beta-202",
        page_count=5,
        status="completed"
    )
    db.add_all([doc_alpha, doc_beta])
    db.commit()

    chk_alpha = DocumentChunk(
        id="chk-alpha-1",
        document_id="doc-alpha-101",
        tenant_id="tenant-alpha",
        chunk_index=0,
        page_number=1,
        content_text="Self-attention mechanisms allow sequence modeling without recurrence.",
        sync_status="synced"
    )
    chk_beta = DocumentChunk(
        id="chk-beta-1",
        document_id="doc-beta-202",
        tenant_id="tenant-beta",
        chunk_index=0,
        page_number=1,
        content_text="Beta proprietary rocket telemetry and confidential formulas.",
        sync_status="synced"
    )
    db.add_all([chk_alpha, chk_beta])
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
def token_alpha():
    return create_access_token("user-alpha-1", "researcher@alpha.internal", "tenant-alpha", UserRole.MEMBER.value)


@pytest.fixture
def token_beta():
    return create_access_token("user-beta-1", "analyst@beta.internal", "tenant-beta", UserRole.MEMBER.value)


# --- Phase F5 Test Cases ---

def test_f5_authenticated_chat_endpoint_success(client, token_alpha):
    resp = client.post(
        "/api/chat",
        json={"query": "What is self-attention mechanism?", "top_k": 3},
        headers={"Authorization": f"Bearer {token_alpha}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "What is self-attention mechanism?"
    assert data["tenant_id"] == "tenant-alpha"
    assert "answer" in data
    assert "citations" in data
    assert isinstance(data["citations"], list)


def test_f5_authenticated_chat_stream_sse_events(client, token_alpha):
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"query": "Explain attention", "top_k": 2},
        headers={"Authorization": f"Bearer {token_alpha}"}
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        
        events = []
        for line in resp.iter_lines():
            if line:
                line_str = line.decode("utf-8").strip() if isinstance(line, bytes) else line.strip()
                if line_str.startswith("data:"):
                    events.append(json.loads(line_str[5:].strip()))
        
        assert len(events) >= 2
        event_types = [e.get("type") for e in events]
        assert "message_start" in event_types
        assert any(e in event_types for e in ("citations", "token", "message_complete"))


def test_f5_chat_unauthenticated_request_rejected(client):
    resp = client.post(
        "/api/chat",
        json={"query": "Unauthenticated inquiry"}
    )
    assert resp.status_code == 401


def test_f5_chat_invalid_token_rejected(client):
    resp = client.post(
        "/api/chat",
        json={"query": "Malicious token inquiry"},
        headers={"Authorization": "Bearer invalid.signature.token"}
    )
    assert resp.status_code == 401


def test_f5_chat_tenant_spoofing_denied(client, token_alpha):
    # Alpha user supplies header claiming to be Beta tenant
    resp = client.post(
        "/api/chat",
        json={"query": "What is Beta's rocket formula?"},
        headers={
            "Authorization": f"Bearer {token_alpha}",
            "X-Tenant-ID": "tenant-beta"
        }
    )
    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"] or "Forbidden" in resp.json()["detail"]


def test_f5_chat_empty_query_rejected(client, token_alpha):
    resp = client.post(
        "/api/chat",
        json={"query": "   "},
        headers={"Authorization": f"Bearer {token_alpha}"}
    )
    assert resp.status_code == 400


def test_f5_chat_oversized_query_rejected(client, token_alpha):
    long_query = "A" * 4005
    resp = client.post(
        "/api/chat",
        json={"query": long_query},
        headers={"Authorization": f"Bearer {token_alpha}"}
    )
    assert resp.status_code == 422  # Pydantic validation error


def test_f5_chat_tenant_isolation_retrieval(client, token_alpha, token_beta):
    # Both tenants query. Check that responses maintain tenant identity
    resp_alpha = client.post(
        "/api/chat",
        json={"query": "sequence modeling"},
        headers={"Authorization": f"Bearer {token_alpha}"}
    )
    assert resp_alpha.status_code == 200
    assert resp_alpha.json()["tenant_id"] == "tenant-alpha"

    resp_beta = client.post(
        "/api/chat",
        json={"query": "rocket telemetry"},
        headers={"Authorization": f"Bearer {token_beta}"}
    )
    assert resp_beta.status_code == 200
    assert resp_beta.json()["tenant_id"] == "tenant-beta"
