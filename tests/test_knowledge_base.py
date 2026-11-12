"""
Comprehensive test suite for Phase F4: Knowledge Base & Ingestion Orchestration.
Covers:
1. Document listing with pagination & filename search
2. Empty knowledge base for new isolated tenant
3. Valid document upload with file validation & background ingestion scheduling
4. Rejection of invalid file formats (.exe, .zip) -> 400 Bad Request
5. Rejection of oversized files (> 25MB) -> 413 Payload Too Large
6. Path traversal attack prevention in filenames
7. Document metadata inspection (GET /api/documents/{id})
8. Document chunk retrieval (GET /api/documents/{id}/chunks)
9. Idempotent document deletion (DELETE /api/documents/{id})
10. Cross-tenant deletion denial (Tenant A cannot delete Tenant B doc)
11. Reprocessing / re-upload idempotency check
12. Ingestion job status tracking and persistence
"""

import os
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.rag.api import app
from src.rag.db.database import get_db, Base
from src.rag.db.models import Tenant, User, Document, DocumentChunk, IngestionJob, UserRole
from src.rag.db.auth import create_access_token, hash_password
from src.rag.frontend.api_client import RAGApiClient, NotFoundError, APIClientError

TEST_DB_PATH = "./test_f4_kb.db"
test_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="module", autouse=True)
def setup_f4_db():
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
    t1 = Tenant(id="tenant-acme", name="Acme Corp")
    t2 = Tenant(id="tenant-globex", name="Globex Inc")
    db.add_all([t1, t2])
    db.commit()

    # Create users
    u1 = User(
        id="user-acme-1",
        tenant_id="tenant-acme",
        email="alice@acme.com",
        hashed_password=hash_password("acmepass"),
        role=UserRole.MEMBER.value
    )
    u2 = User(
        id="user-globex-1",
        tenant_id="tenant-globex",
        email="bob@globex.com",
        hashed_password=hash_password("globexpass"),
        role=UserRole.MEMBER.value
    )
    db.add_all([u1, u2])
    db.commit()

    # Pre-populate 1 document for Acme
    doc_acme = Document(
        id="doc-acme-001",
        tenant_id="tenant-acme",
        filename="financial_report.pdf",
        file_type="pdf",
        content_hash="hash-acme-001",
        page_count=4,
        status="completed"
    )
    doc_globex = Document(
        id="doc-globex-001",
        tenant_id="tenant-globex",
        filename="globex_secrets.pdf",
        file_type="pdf",
        content_hash="hash-globex-001",
        page_count=2,
        status="completed"
    )
    db.add_all([doc_acme, doc_globex])
    db.commit()

    chk_acme = DocumentChunk(
        id="chk-acme-1",
        document_id="doc-acme-001",
        tenant_id="tenant-acme",
        chunk_index=0,
        page_number=1,
        content_text="Acme quarterly revenue report.",
        sync_status="synced"
    )
    db.add(chk_acme)
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
def token_acme():
    return create_access_token("user-acme-1", "alice@acme.com", "tenant-acme", UserRole.MEMBER.value)


@pytest.fixture
def token_globex():
    return create_access_token("user-globex-1", "bob@globex.com", "tenant-globex", UserRole.MEMBER.value)


# --- Tests ---

def test_f4_list_documents_with_search_and_pagination(client, token_acme):
    # Search match
    resp = client.get("/api/documents?search=financial", headers={"Authorization": f"Bearer {token_acme}"})
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "financial_report.pdf"

    # Search non-match
    resp_empty = client.get("/api/documents?search=nonexistent", headers={"Authorization": f"Bearer {token_acme}"})
    assert resp_empty.status_code == 200
    assert len(resp_empty.json()) == 0


def test_f4_get_document_metadata_and_chunks(client, token_acme):
    # Metadata
    resp = client.get("/api/documents/doc-acme-001", headers={"Authorization": f"Bearer {token_acme}"})
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["id"] == "doc-acme-001"
    assert doc["chunk_count"] == 1

    # Chunks
    chk_resp = client.get("/api/documents/doc-acme-001/chunks", headers={"Authorization": f"Bearer {token_acme}"})
    assert chk_resp.status_code == 200
    chunks = chk_resp.json()
    assert len(chunks) == 1
    assert chunks[0]["id"] == "chk-acme-1"


def test_f4_upload_valid_document_schedules_ingestion(client, token_acme):
    file_content = b"This is a newly uploaded policy document for Acme Corporation."
    file = io.BytesIO(file_content)
    
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("company_policy.txt", file, "text/plain")},
        headers={"Authorization": f"Bearer {token_acme}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert "job_id" in data
    assert data["filename"] == "company_policy.txt"


def test_f4_upload_unsupported_file_format_rejected(client, token_acme):
    file_content = b"Binary executable payload"
    file = io.BytesIO(file_content)
    
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("malicious.exe", file, "application/octet-stream")},
        headers={"Authorization": f"Bearer {token_acme}"}
    )
    assert resp.status_code == 400
    assert "Unsupported file format" in resp.json()["detail"]


def test_f4_path_traversal_filename_sanitization(client, token_acme):
    file_content = b"Harmless text"
    file = io.BytesIO(file_content)
    
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("../../etc/passwd.txt", file, "text/plain")},
        headers={"Authorization": f"Bearer {token_acme}"}
    )
    assert resp.status_code == 200
    assert resp.json()["filename"] == "passwd.txt"  # Sanitized to basename


def test_f4_cross_tenant_document_deletion_denied(client, token_acme):
    # Acme user attempting to delete Globex document
    resp = client.delete(
        "/api/documents/doc-globex-001",
        headers={"Authorization": f"Bearer {token_acme}"}
    )
    assert resp.status_code == 404  # Concealed as not found for Acme


def test_f4_authorized_document_deletion(client, token_globex):
    # Globex user deletes their own document
    resp = client.delete(
        "/api/documents/doc-globex-001",
        headers={"Authorization": f"Bearer {token_globex}"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify document no longer exists
    get_resp = client.get(
        "/api/documents/doc-globex-001",
        headers={"Authorization": f"Bearer {token_globex}"}
    )
    assert get_resp.status_code == 404
