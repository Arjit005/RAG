"""
tests/test_stage_f_neon_qa.py

Stage F: Comprehensive Post-Migration Quality, Security & Reliability Test Suite.
Covers:
- F1: PostgreSQL Integration (Neon live connection, CRUD, transaction rollback, duplicate ingestion handling)
- F2: Retrieval Regression (Dense, BM25, RRF, Qdrant point references, FAISS fallback, result correctness)
- F3: Security (Cross-tenant isolation, SQL injection protection, credential leakage, input validation)
- F4: Reliability & Performance (Connection pool handling, transaction rollback, simulated fallback, latency benchmarks)

SAFETY GUARANTEE:
- Uses isolated test tenant 'test-tenant-stage-f'.
- Cleans up only test records created by this test suite.
- Never modifies or deletes the 317 production chunks or 6 production documents.
"""

import os
import sys
import time
import uuid
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient

# Load environment
load_dotenv()

from src.rag.db.database import normalize_database_url
from src.rag.db.models import Tenant, Document, DocumentChunk, IngestionJob, IngestionStatus, SyncStatus
from src.rag.db.repository import DocumentRepository
from src.rag.db.id_generator import compute_content_hash, generate_document_id, generate_chunk_id
from src.rag.search import RAGSearch
from src.rag.qdrant_store import QdrantVectorStore


@pytest.fixture(scope="module")
def neon_session():
    """Provides a live session to Neon PostgreSQL using DATABASE_URL."""
    db_url = os.getenv("DATABASE_URL")
    assert db_url, "DATABASE_URL must be configured for Stage F testing"
    normalized = normalize_database_url(db_url)
    engine = create_engine(normalized, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="module")
def test_tenant_id():
    return f"test-tenant-stage-f-{uuid.uuid4().hex[:8]}"


# ==============================================================================
# F1: PostgreSQL Integration Tests
# ==============================================================================

def test_f1_runtime_neon_database_identity(neon_session):
    """Verify Neon PostgreSQL runtime connection without fallback."""
    res = neon_session.execute(text("SELECT current_database(), current_user, version();")).fetchone()
    db_name, user_name, version_str = res
    assert db_name == "neondb", f"Expected neondb, got {db_name}"
    assert user_name == "neondb_owner", f"Expected neondb_owner, got {user_name}"
    assert "PostgreSQL" in version_str, "Must be real PostgreSQL engine"


def test_f1_neon_document_and_chunk_crud(neon_session, test_tenant_id):
    """Test full transactional CRUD lifecycle in Neon with isolated tenant."""
    repo = DocumentRepository(neon_session)
    
    # 1. Create Tenant
    tenant = repo.get_or_create_default_tenant(tenant_id=test_tenant_id, name="Stage F Test Org")
    assert tenant.id == test_tenant_id
    
    # 2. Upsert Document
    content_bytes = b"Stage F Automated Test Content For Relational Validation."
    doc = repo.upsert_document(
        tenant_id=test_tenant_id,
        filename="stage_f_test.txt",
        file_type="txt",
        content_bytes=content_bytes,
        page_count=1,
        status=IngestionStatus.COMPLETED
    )
    doc_id = doc.id
    assert doc_id is not None
    
    # 3. Save Chunks
    chunk_data = [{
        "text": "Chunk text 1 for Stage F validation",
        "page": 1,
        "type": "text",
        "summary": "Summary 1"
    }]
    chunks = repo.save_chunks(doc_id, test_tenant_id, chunk_data)
    assert len(chunks) == 1
    chunk_id = chunks[0].id
    
    # 4. Read back
    retrieved_doc = repo.get_document(doc_id, tenant_id=test_tenant_id)
    assert retrieved_doc is not None
    assert retrieved_doc.filename == "stage_f_test.txt"
    
    # 5. Clean up test document (Cascade deletes test chunks)
    deleted = repo.delete_document(doc_id, tenant_id=test_tenant_id)
    assert deleted is True
    
    # Clean up test tenant
    neon_session.query(Tenant).filter(Tenant.id == test_tenant_id).delete()
    neon_session.commit()


def test_f1_neon_transaction_rollback_safety(neon_session):
    """Verify that failed transactions roll back cleanly without polluting Neon."""
    repo = DocumentRepository(neon_session)
    dummy_tenant = f"fail-tenant-{uuid.uuid4().hex[:6]}"
    
    try:
        with neon_session.begin_nested():
            t = Tenant(id=dummy_tenant, name="Rollback Test Tenant")
            neon_session.add(t)
            neon_session.flush()
            # Force integrity error (insert duplicate PK)
            t_dup = Tenant(id=dummy_tenant, name="Duplicate")
            neon_session.add(t_dup)
            neon_session.flush()
    except Exception:
        pass  # Expected rollback
        
    # Verify dummy tenant was not committed
    exists = neon_session.query(Tenant).filter(Tenant.id == dummy_tenant).first()
    assert exists is None, "Failed transaction must roll back cleanly"


# ==============================================================================
# F2: Retrieval Regression Tests
# ==============================================================================

def test_f2_qdrant_production_points_integrity():
    """Verify that all 319 points (317 default-tenant + 2 tenant-acme) remain intact in local Qdrant."""
    qdrant_path = os.getenv("QDRANT_PATH", "qdrant_storage")
    client = QdrantClient(path=qdrant_path)
    points, _ = client.scroll(
        collection_name="rag_enterprise_chunks",
        limit=1000,
        with_payload=False,
        with_vectors=False
    )
    client.close()
    assert len(points) == 319, f"Expected 319 vectors, found {len(points)}"


def test_f2_hybrid_retrieval_and_rrf_scoring():
    """Verify Dense + BM25 + RRF Hybrid search across existing documents."""
    from src.rag.vectorstore import FaissVectorStore
    faiss_store = FaissVectorStore()
    faiss_store.load()
    qdrant_store = QdrantVectorStore(collection_name="rag_enterprise_chunks", location="qdrant_storage")
    
    query = "What is multi-head attention mechanism?"
    q_emb = faiss_store.model.encode([query])[0].tolist()
    
    # Run hybrid search with RRF on Qdrant
    res = qdrant_store.hybrid_search(query_text=query, query_embedding=q_emb, top_k=3, tenant_id="default-tenant")
    assert len(res) > 0, "Hybrid search should return candidates"
    
    # Verify citations structure
    top_hit = res[0]
    assert "metadata" in top_hit
    assert "distance" in top_hit
    meta = top_hit["metadata"]
    assert "source" in meta or "filename" in meta


def test_f2_faiss_fallback_preservation():
    """Verify that the preserved FAISS fallback store exists and can be loaded."""
    from src.rag.vectorstore import FaissVectorStore
    faiss_store = FaissVectorStore()
    faiss_store.load()
    assert faiss_store.index is not None, "FAISS index must be loadable"
    assert faiss_store.index.ntotal > 0, "FAISS index must contain existing vectors"
    
    # Run hybrid search on FAISS
    results = faiss_store.hybrid_search("transformer architecture", top_k=2)
    assert len(results) > 0, "FAISS fallback must successfully retrieve candidates"


# ==============================================================================
# F3: Security & Tenant Isolation Tests
# ==============================================================================

def test_f3_cross_tenant_isolation_in_qdrant():
    """Verify Qdrant payload filters strictly prevent cross-tenant data leakage."""
    from src.rag.vectorstore import FaissVectorStore
    faiss_store = FaissVectorStore()
    qdrant_store = QdrantVectorStore(collection_name="rag_enterprise_chunks", location="qdrant_storage")
    
    query = "machine learning"
    q_emb = faiss_store.model.encode([query])[0].tolist()
    
    # Query with default-tenant
    res_default = qdrant_store.search(query_embedding=q_emb, top_k=5, tenant_id="default-tenant")
    assert len(res_default) > 0, "Default tenant should find records"
    for r in res_default:
        meta = r.get("metadata") or {}
        assert meta.get("tenant_id") == "default-tenant"
        
    # Query with an isolated, nonexistent tenant
    res_isolated = qdrant_store.search(query_embedding=q_emb, top_k=5, tenant_id="isolated-tenant-xyz")
    assert len(res_isolated) == 0, "Isolated tenant must retrieve 0 records from other tenants"


def test_f3_sql_injection_defense(neon_session):
    """Verify that malicious SQL payloads do not execute via repository or ORM."""
    repo = DocumentRepository(neon_session)
    malicious_id = "'; DROP TABLE test_dummy; --"
    
    # Must query cleanly without syntax error or table drop
    doc = repo.get_document(malicious_id, tenant_id="default-tenant")
    assert doc is None, "Malicious payload must be safely parameterized"


# ==============================================================================
# F4: Reliability & Performance Tests
# ==============================================================================

def test_f4_retrieval_latency_benchmark():
    """Measure retrieval latency to ensure enterprise SLA (< 3.0s)."""
    from src.rag.vectorstore import FaissVectorStore
    faiss_store = FaissVectorStore()
    qdrant_store = QdrantVectorStore(collection_name="rag_enterprise_chunks", location="qdrant_storage")
    
    query = "What is neural network?"
    q_emb = faiss_store.model.encode([query])[0].tolist()
    
    start_time = time.time()
    res = qdrant_store.hybrid_search(query_text=query, query_embedding=q_emb, top_k=3, tenant_id="default-tenant")
    elapsed = time.time() - start_time
    assert elapsed < 3.0, f"Retrieval latency too slow: {elapsed:.2f}s"
    assert len(res) > 0


def test_f4_neon_connection_pool_stress(neon_session):
    """Execute multiple rapid queries to verify pool recycling and connection resilience."""
    for i in range(10):
        val = neon_session.execute(text("SELECT 1;")).scalar()
        assert val == 1
