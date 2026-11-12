import pytest
import os
import numpy as np
from src.rag.qdrant_store import QdrantVectorStore

@pytest.fixture(scope="module")
def qdrant_store():
    # Use isolated in-memory Qdrant client for integration tests
    store = QdrantVectorStore(
        collection_name="test_enterprise_qdrant",
        vector_size=4,
        location=":memory:"
    )
    yield store

def test_qdrant_add_and_search_dense(qdrant_store):
    tenant_id = "tenant-finance"
    doc_id = "doc-001"
    chunks = [
        {"id": "chunk-1", "text": "Annual revenue reached 10 million dollars", "page": 1, "type": "text"},
        {"id": "chunk-2", "text": "Operating expenses decreased by 5 percent", "page": 2, "type": "text"}
    ]
    embeddings = [
        [0.1, 0.2, 0.3, 0.4],
        [0.4, 0.3, 0.2, 0.1]
    ]

    chunk_ids = qdrant_store.add_documents(tenant_id, doc_id, chunks, embeddings)
    assert len(chunk_ids) == 2

    # Query with exact vector close to chunk-1
    res = qdrant_store.search(
        query_embedding=[0.1, 0.2, 0.3, 0.4],
        top_k=1,
        tenant_id=tenant_id
    )
    assert len(res) == 1
    assert res[0]["metadata"]["chunk_id"] == chunk_ids[0]
    assert res[0]["metadata"]["text"] == "Annual revenue reached 10 million dollars"

def test_qdrant_tenant_isolation_filter(qdrant_store):
    # Add a document for tenant B
    qdrant_store.add_documents(
        tenant_id="tenant-healthcare",
        document_id="doc-health",
        chunks=[{"id": "chunk-h1", "text": "Patient records and clinical trials", "page": 1, "type": "text"}],
        embeddings=[[0.1, 0.2, 0.3, 0.4]]
    )

    # Tenant finance must NOT receive tenant healthcare documents even with identical query vector
    res_finance = qdrant_store.search(
        query_embedding=[0.1, 0.2, 0.3, 0.4],
        top_k=5,
        tenant_id="tenant-finance"
    )
    for r in res_finance:
        assert r["metadata"]["tenant_id"] == "tenant-finance"
        assert r["metadata"]["chunk_id"] != "chunk-h1"

def test_qdrant_hybrid_search(qdrant_store):
    res = qdrant_store.hybrid_search(
        query_text="operating expenses",
        query_embedding=[0.4, 0.3, 0.2, 0.1],
        top_k=1,
        tenant_id="tenant-finance"
    )
    assert len(res) == 1
    assert "Operating expenses" in res[0]["metadata"]["text"]

def test_qdrant_document_deletion_cascade(qdrant_store):
    qdrant_store.delete_document("doc-001", tenant_id="tenant-finance")
    res = qdrant_store.search(
        query_embedding=[0.1, 0.2, 0.3, 0.4],
        top_k=5,
        tenant_id="tenant-finance"
    )
    assert len(res) == 0
