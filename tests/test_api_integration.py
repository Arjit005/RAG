"""
Comprehensive test suite for Phase F3: FastAPI Read-Only Integration & Security Endpoints.
Uses a file-based temporary SQLite database (./test_api_integration.db) to ensure connection sharing.
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.rag.api import app
from src.rag.db.database import get_db, Base
from src.rag.db.models import Tenant, Document, DocumentChunk, IngestionJob, User, UserRole
from src.rag.db.auth import create_access_token, hash_password
from src.rag.frontend.api_client import (
    RAGApiClient,
    NotFoundError,
    AuthenticationError,
    ServiceUnavailableError,
    APIClientError
)

TEST_DB_PATH = "./test_api_integration.db"
test_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    
    # Create test tenants
    tenant_default = Tenant(id="default-tenant", name="Default Org")
    tenant_isolated = Tenant(id="isolated-tenant", name="Isolated Org")
    db.add_all([tenant_default, tenant_isolated])
    
    # Create test users for authentication
    user_default = User(
        id="user-default-1",
        email="default@org.com",
        tenant_id="default-tenant",
        role=UserRole.MEMBER.value,
        hashed_password=hash_password("password123")
    )
    user_isolated = User(
        id="user-isolated-1",
        email="isolated@org.com",
        tenant_id="isolated-tenant",
        role=UserRole.MEMBER.value,
        hashed_password=hash_password("password123")
    )
    db.add_all([user_default, user_isolated])
    db.commit()

    # Create documents for default-tenant
    doc1 = Document(
        id="doc-001",
        tenant_id="default-tenant",
        filename="test_report.pdf",
        file_type="pdf",
        content_hash="hash-001",
        page_count=5,
        status="completed"
    )
    doc2 = Document(
        id="doc-002",
        tenant_id="default-tenant",
        filename="notes.txt",
        file_type="txt",
        content_hash="hash-002",
        page_count=1,
        status="completed"
    )
    # Create document for isolated-tenant
    doc_iso = Document(
        id="doc-iso",
        tenant_id="isolated-tenant",
        filename="secret.pdf",
        file_type="pdf",
        content_hash="hash-iso",
        page_count=2,
        status="completed"
    )
    db.add_all([doc1, doc2, doc_iso])
    db.commit()

    # Create chunks for doc1
    chunk1 = DocumentChunk(
        id="chunk-001",
        document_id="doc-001",
        tenant_id="default-tenant",
        chunk_index=0,
        page_number=1,
        chunk_type="text",
        content_text="Sample text content for chunk 1",
        sync_status="synced"
    )
    chunk2 = DocumentChunk(
        id="chunk-002",
        document_id="doc-001",
        tenant_id="default-tenant",
        chunk_index=1,
        page_number=2,
        chunk_type="text",
        content_text="Sample text content for chunk 2",
        sync_status="synced"
    )
    db.add_all([chunk1, chunk2])

    # Create a job for default-tenant
    job = IngestionJob(
        id="job-001",
        tenant_id="default-tenant",
        document_id="doc-001",
        status="completed",
        progress_percent=100
    )
    db.add(job)
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
def token_default():
    return create_access_token(
        user_id="user-default-1",
        email="default@org.com",
        tenant_id="default-tenant",
        role=UserRole.MEMBER.value
    )


@pytest.fixture
def token_isolated():
    return create_access_token(
        user_id="user-isolated-1",
        email="isolated@org.com",
        tenant_id="isolated-tenant",
        role=UserRole.MEMBER.value
    )


# --- Endpoint Tests ---

def test_list_documents_valid(client, token_default):
    response = client.get("/api/documents", headers={"Authorization": f"Bearer {token_default}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    filenames = [d["filename"] for d in data]
    assert "test_report.pdf" in filenames
    assert "notes.txt" in filenames
    doc_report = next(d for d in data if d["filename"] == "test_report.pdf")
    assert doc_report["chunk_count"] == 2


def test_list_documents_empty_for_empty_tenant(client):
    db = TestingSessionLocal()
    db.add(Tenant(id="empty-tenant", name="Empty Org"))
    db.add(User(
        id="user-empty-1",
        email="empty@org.com",
        tenant_id="empty-tenant",
        role=UserRole.MEMBER.value,
        hashed_password=hash_password("password123")
    ))
    db.commit()
    db.close()

    empty_token = create_access_token(
        user_id="user-empty-1",
        email="empty@org.com",
        tenant_id="empty-tenant",
        role=UserRole.MEMBER.value
    )

    response = client.get("/api/documents", headers={"Authorization": f"Bearer {empty_token}"})
    assert response.status_code == 200
    assert response.json() == []


def test_list_documents_cross_tenant_isolation(client, token_isolated):
    response = client.get("/api/documents", headers={"Authorization": f"Bearer {token_isolated}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["filename"] == "secret.pdf"
    assert "test_report.pdf" not in [d["filename"] for d in data]


def test_unauthorized_nonexistent_tenant_fails_closed(client, token_default):
    # Tenant A attempts to spoof tenant header
    response = client.get("/api/documents", headers={
        "Authorization": f"Bearer {token_default}",
        "X-Tenant-ID": "malicious-tenant-injection"
    })
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]


def test_get_document_chunks_valid(client, token_default):
    response = client.get("/api/documents/doc-001/chunks", headers={"Authorization": f"Bearer {token_default}"})
    assert response.status_code == 200
    chunks = response.json()
    assert len(chunks) == 2
    assert chunks[0]["id"] == "chunk-001"
    assert chunks[1]["id"] == "chunk-002"


def test_get_document_chunks_not_found(client, token_default):
    response = client.get("/api/documents/non-existent-doc/chunks", headers={"Authorization": f"Bearer {token_default}"})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_document_chunks_cross_tenant_denial(client, token_default):
    response = client.get("/api/documents/doc-iso/chunks", headers={"Authorization": f"Bearer {token_default}"})
    assert response.status_code == 404


def test_get_metrics_summary(client, token_default):
    response = client.get("/api/metrics/summary", headers={"Authorization": f"Bearer {token_default}"})
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["tenant_id"] == "default-tenant"
    assert metrics["total_documents"] == 2
    assert metrics["total_chunks"] == 2
    assert metrics["active_jobs_count"] == 0


def test_list_pipeline_jobs(client, token_default):
    response = client.get("/api/pipeline/jobs", headers={"Authorization": f"Bearer {token_default}"})
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == "job-001"
    assert jobs[0]["status"] == "completed"


def test_sql_injection_in_headers_and_params(client, token_default):
    malicious = "'; DROP TABLE documents; --"
    resp = client.get(f"/api/documents/{malicious}/chunks", headers={"Authorization": f"Bearer {token_default}"})
    assert resp.status_code == 404


# --- Frontend API Client Unit Tests ---

def test_api_client_initialization_and_url():
    client = RAGApiClient(base_url="http://localhost:8000/")
    assert client.base_url == "http://localhost:8000"
    assert client.timeout == 15.0


def test_api_client_error_handling_404():
    unreachable_client = RAGApiClient(base_url="http://127.0.0.1:59999", timeout=0.5)
    with pytest.raises(APIClientError):
        unreachable_client.get_health()
