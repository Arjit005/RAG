import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.rag.db.database import Base
from src.rag.db.models import Tenant, Document, DocumentChunk, IngestionStatus, SyncStatus
from src.rag.db.repository import DocumentRepository
from src.rag.db.id_generator import generate_document_id, generate_chunk_id, compute_content_hash

TEST_DB_PATH = "./test_storage_foundation.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

@pytest.fixture(scope="module")
def db_session():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

def test_tenant_creation_and_isolation(db_session):
    repo = DocumentRepository(db_session)
    tenant_a = repo.get_or_create_default_tenant("org-alpha", "Alpha Corp")
    tenant_b = repo.get_or_create_default_tenant("org-beta", "Beta LLC")
    assert tenant_a.id == "org-alpha"
    assert tenant_b.id == "org-beta"

def test_document_stable_uuid_and_idempotent_upsert(db_session):
    repo = DocumentRepository(db_session)
    dummy_file = b"This is a test document on enterprise storage."
    doc1 = repo.upsert_document(
        tenant_id="org-alpha",
        filename="test_doc.pdf",
        file_type="pdf",
        content_bytes=dummy_file,
        page_count=3
    )
    assert doc1.id is not None
    assert doc1.tenant_id == "org-alpha"
    assert doc1.page_count == 3

    # Re-upserting identical content must return exact same stable UUID
    doc2 = repo.upsert_document(
        tenant_id="org-alpha",
        filename="test_doc.pdf",
        file_type="pdf",
        content_bytes=dummy_file,
        page_count=3
    )
    assert doc1.id == doc2.id
    assert doc1.content_hash == doc2.content_hash

def test_chunk_lifecycle_and_deletion_cascade(db_session):
    repo = DocumentRepository(db_session)
    dummy_file = b"Unique content for chunk testing"
    doc = repo.upsert_document(
        tenant_id="org-alpha",
        filename="chunk_test.pdf",
        file_type="pdf",
        content_bytes=dummy_file,
        page_count=2
    )

    chunks_data = [
        {"type": "text", "page": 1, "text": "Page 1 intro"},
        {"type": "table", "page": 2, "text": "| A | B |\n|---|---|\n| 1 | 2 |", "summary": "Table summary"},
        {"type": "image", "page": 2, "text": "Visual summary", "image_path": "data/extracted_images/fig1.png"}
    ]

    chunks = repo.save_chunks(doc.id, "org-alpha", chunks_data)
    assert len(chunks) == 3
    assert chunks[0].chunk_type == "text"
    assert chunks[1].chunk_type == "table"
    assert chunks[2].chunk_type == "image"
    assert chunks[0].sync_status == SyncStatus.PENDING.value

    # Update sync status
    repo.update_chunks_sync_status([c.id for c in chunks], SyncStatus.SYNCED)
    reloaded_chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).all()
    for c in reloaded_chunks:
        assert c.sync_status == SyncStatus.SYNCED.value

    # Test delete cascade
    deleted = repo.delete_document(doc.id, "org-alpha")
    assert deleted is True
    # Chunks must be deleted
    remaining_chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).all()
    assert len(remaining_chunks) == 0
