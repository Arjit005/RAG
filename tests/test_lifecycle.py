import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.rag.db.database import Base
from src.rag.db.models import IngestionStatus, SyncStatus, DocumentChunk
from src.rag.db.lifecycle import DocumentLifecycleService
from src.rag.qdrant_store import QdrantVectorStore

TEST_DB_PATH = "./test_lifecycle.db"

class MockEmbeddingPipeline:
    def __init__(self):
        class MockModel:
            def encode(self, texts, **kwargs):
                import numpy as np
                # Deterministic normalized vectors for testing
                vecs = []
                for idx, t in enumerate(texts):
                    v = np.zeros(384, dtype=float)
                    val = (hash(t) % 1000) / 1000.0
                    v[0] = val
                    v[1] = 1.0 - val
                    vecs.append(v)
                return np.array(vecs)
        self.model = MockModel()

@pytest.fixture(scope="module")
def lifecycle_env():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    vector_store = QdrantVectorStore(
        collection_name="test_lifecycle_chunks",
        vector_size=384,
        location=":memory:"
    )

    emb_pipeline = MockEmbeddingPipeline()
    service = DocumentLifecycleService(session, vector_store, emb_pipeline)

    yield service, session, vector_store

    session.close()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

def test_full_document_lifecycle_ingest_and_search(lifecycle_env):
    service, session, vector_store = lifecycle_env
    tenant_id = "tenant-enterprise"
    raw_content = b"Transformer architectures use multi-head self-attention mechanisms to process sequential tokens."

    chunks_data = [
        {
            "chunk_index": 0,
            "page": 1,
            "type": "text",
            "text": "Transformer architectures use multi-head self-attention mechanisms to process sequential tokens."
        }
    ]

    doc = service.ingest_document(
        tenant_id=tenant_id,
        filename="transformer_paper.pdf",
        file_type="pdf",
        content_bytes=raw_content,
        raw_chunks=chunks_data,
        page_count=1
    )

    assert doc.status == IngestionStatus.COMPLETED.value

    # Verify search
    query_emb = service.embedding_pipeline.model.encode(["attention mechanism"]).tolist()
    search_res = vector_store.search(query_emb, top_k=1, tenant_id=tenant_id)
    assert len(search_res) == 1
    assert "Transformer architectures" in search_res[0]["metadata"]["text"]

def test_document_lifecycle_cascade_delete(lifecycle_env):
    service, session, vector_store = lifecycle_env
    tenant_id = "tenant-enterprise"

    # Ingest document to delete
    raw_content = b"Content to be deleted immediately."
    doc = service.ingest_document(
        tenant_id=tenant_id,
        filename="delete_me.pdf",
        file_type="pdf",
        content_bytes=raw_content,
        raw_chunks=[{"chunk_index": 0, "page": 1, "type": "text", "text": "Content to be deleted immediately."}],
        page_count=1
    )

    deleted = service.delete_document(doc.id, tenant_id)
    assert deleted is True

    # Search should return zero points
    query_emb = service.embedding_pipeline.model.encode(["deleted immediately"]).tolist()
    res = vector_store.search(query_emb, top_k=5, tenant_id=tenant_id)
    for r in res:
        assert r["metadata"]["document_id"] != doc.id
