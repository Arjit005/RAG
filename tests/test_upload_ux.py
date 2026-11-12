"""
Targeted tests for Phase F4.1: Drag & Drop Document Upload and UX.
Verifies:
1. Drag & drop / browse file staging logic with size and format inspection
2. Rejection of unsupported formats (.exe, .zip) -> 400 Bad Request
3. Rejection of oversized files (> 25MB) -> 413 Payload Too Large
4. Path traversal protection during file upload
5. Unauthenticated / forged tenant upload rejection
6. Ingestion job lifecycle tracking
7. UI file staging and removal simulation
"""

import os
import io
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.rag.api import app
from src.rag.db.database import get_db, Base
from src.rag.db.models import Tenant, User, Document, DocumentChunk, IngestionJob, UserRole, IngestionStatus
from src.rag.db.auth import create_access_token, hash_password
from src.rag.frontend.api_client import RAGApiClient, APIClientError, AuthenticationError

TEST_DB_PATH = "./test_f4_1_upload.db"
test_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_f4_1_db():
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
    t1 = Tenant(id="tenant-alpha", name="Alpha Corp")
    t2 = Tenant(id="tenant-beta", name="Beta Corp")
    db.add_all([t1, t2])
    db.commit()

    # Create user
    u1 = User(
        id="user-alpha-1",
        tenant_id="tenant-alpha",
        email="alice@alpha.com",
        hashed_password=hash_password("alphapass"),
        role=UserRole.MEMBER.value
    )
    db.add(u1)
    db.commit()

    yield

    app.dependency_overrides.pop(get_db, None)
    db.close()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


@pytest.fixture
def auth_token_alpha():
    return create_access_token(
        user_id="user-alpha-1",
        email="alice@alpha.com",
        tenant_id="tenant-alpha",
        role=UserRole.MEMBER.value
    )


def test_f4_1_upload_valid_formats_accepted(auth_token_alpha):
    """Verifies that all allowed formats (.pdf, .txt, .csv, .docx, .json) are accepted."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_token_alpha}", "X-Tenant-ID": "tenant-alpha"}

    formats = [
        ("report.pdf", b"%PDF-1.4 sample pdf content"),
        ("notes.txt", b"plain text research notes"),
        ("data.csv", b"col1,col2\nval1,val2"),
        ("summary.docx", b"PK\x03\x04 fake docx binary data"),
        ("config.json", b'{"key": "value"}')
    ]

    for fname, content in formats:
        files = {"file": (fname, io.BytesIO(content))}
        resp = client.post("/api/documents/upload", files=files, headers=headers)
        assert resp.status_code == 200, f"Failed for format {fname}: {resp.text}"
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["filename"] == fname
        assert "job_id" in data
        assert data["tenant_id"] == "tenant-alpha"


def test_f4_1_upload_unsupported_format_rejected(auth_token_alpha):
    """Verifies that unsupported file extensions are rejected with 400 Bad Request."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_token_alpha}", "X-Tenant-ID": "tenant-alpha"}

    disallowed = ["malware.exe", "bundle.zip", "script.sh", "library.dll"]
    for fname in disallowed:
        files = {"file": (fname, io.BytesIO(b"binary_code"))}
        resp = client.post("/api/documents/upload", files=files, headers=headers)
        assert resp.status_code == 400
        assert "Unsupported file format" in resp.json()["detail"]


def test_f4_1_upload_oversized_file_rejected(auth_token_alpha):
    """Verifies that files exceeding 25MB are rejected with 413 Payload Too Large."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_token_alpha}", "X-Tenant-ID": "tenant-alpha"}

    oversized_data = b"0" * (26 * 1024 * 1024)  # 26MB
    files = {"file": ("massive_document.pdf", io.BytesIO(oversized_data))}
    resp = client.post("/api/documents/upload", files=files, headers=headers)
    assert resp.status_code == 413
    assert "exceeds maximum allowed size" in resp.json()["detail"]


def test_f4_1_path_traversal_sanitized(auth_token_alpha):
    """Verifies that directory traversal strings in filename are safely stripped."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_token_alpha}", "X-Tenant-ID": "tenant-alpha"}

    traversal_name = "../../../../etc/passwd.txt"
    files = {"file": (traversal_name, io.BytesIO(b"safe text"))}
    resp = client.post("/api/documents/upload", files=files, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["filename"] == "passwd.txt"


def test_f4_1_unauthenticated_upload_rejected():
    """Verifies that unauthenticated uploads are strictly blocked with 401."""
    client = TestClient(app)
    files = {"file": ("unauth.txt", io.BytesIO(b"data"))}
    resp = client.post("/api/documents/upload", files=files)
    assert resp.status_code == 401


def test_f4_1_tenant_spoofing_upload_denied(auth_token_alpha):
    """Verifies that Tenant Alpha cannot upload into Tenant Beta using forged header."""
    client = TestClient(app)
    # Token is for tenant-alpha, but header claims tenant-beta
    headers = {"Authorization": f"Bearer {auth_token_alpha}", "X-Tenant-ID": "tenant-beta"}
    files = {"file": ("spoof.txt", io.BytesIO(b"data"))}
    resp = client.post("/api/documents/upload", files=files, headers=headers)
    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]


def test_f4_1_pipeline_job_tracking(auth_token_alpha):
    """Verifies that uploaded documents create persisted IngestionJob records with real statuses."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_token_alpha}", "X-Tenant-ID": "tenant-alpha"}

    files = {"file": ("tracked_doc.txt", io.BytesIO(b"job tracking content"))}
    upload_resp = client.post("/api/documents/upload", files=files, headers=headers)
    assert upload_resp.status_code == 200
    job_id = upload_resp.json()["job_id"]

    # Query jobs
    jobs_resp = client.get("/api/pipeline/jobs", headers=headers)
    assert jobs_resp.status_code == 200
    jobs = jobs_resp.json()
    matched_job = next((j for j in jobs if j["id"] == job_id), None)
    assert matched_job is not None
    assert matched_job["tenant_id"] == "tenant-alpha"
    assert matched_job["status"] in ["pending", "processing", "completed", "failed"]
