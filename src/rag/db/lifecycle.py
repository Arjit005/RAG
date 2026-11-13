import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.rag.db.models import Document, DocumentChunk, IngestionStatus, SyncStatus
from src.rag.db.repository import DocumentRepository
from src.rag.vectorstore_base import BaseVectorStore

logger = logging.getLogger(__name__)
class DocumentLifecycleService:
    """
    Coordinates atomic document metadata transactions in PostgreSQL
    with idempotent vector index synchronization in Qdrant/FAISS.
    """
    def __init__(
        self,
        db_session: Session,
        vector_store: BaseVectorStore,
        embedding_pipeline: Optional[Any] = None
    ):
        self.db = db_session
        self.repo = DocumentRepository(db_session)
        self.vector_store = vector_store
        self._embedding_pipeline = embedding_pipeline

    @property
    def embedding_pipeline(self):
        if self._embedding_pipeline is None:
            from src.rag.embedding import EmbeddingPipeline
            self._embedding_pipeline = EmbeddingPipeline()
        return self._embedding_pipeline

    def ingest_document(
        self,
        tenant_id: str,
        filename: str,
        file_type: str,
        content_bytes: bytes,
        raw_chunks: List[Dict[str, Any]],
        page_count: int = 1
    ) -> Document:
        """
        Idempotent document ingestion:
        1. Upsert Document in PostgreSQL
        2. Save DocumentChunks in PostgreSQL (SyncStatus: PENDING)
        3. Generate dense embeddings for chunks
        4. Upsert vectors with metadata into VectorStore
        5. Mark DocumentChunks as SYNCED and Document as COMPLETED
        """
        # Step 1: Canonical relational record
        doc = self.repo.upsert_document(
            tenant_id=tenant_id,
            filename=filename,
            file_type=file_type,
            content_bytes=content_bytes,
            page_count=page_count,
            status=IngestionStatus.PROCESSING
        )

        # Step 2: Save chunk records
        chunks = self.repo.save_chunks(doc.id, tenant_id, raw_chunks)
        if not chunks:
            logger.warning(f"Ingestion produced no chunks for doc {doc.id}")
            doc.status = IngestionStatus.FAILED.value
            self.db.commit()
            raise ValueError(f"Document '{filename}' could not be chunked or contained no readable text.")

        # Step 3 & 4: Embed chunk texts and Synchronize to Vector Store
        try:
            embed_texts = [c.summary_text if (c.chunk_type == "table" and c.summary_text) else c.content_text for c in chunks]
            batch_size = 8
            embeddings = []
            import gc
            for i in range(0, len(embed_texts), batch_size):
                batch = embed_texts[i:i+batch_size]
                batch_embeddings = self.embedding_pipeline.model.encode(batch, show_progress_bar=False).tolist()
                embeddings.extend(batch_embeddings)
                gc.collect()

            chunks_payload = [
                {
                    "id": c.id,
                    "chunk_index": c.chunk_index,
                    "page": c.page_number,
                    "type": c.chunk_type,
                    "text": c.content_text,
                    "summary": c.summary_text,
                    "filename": filename,
                    "source": filename,
                    "image_path": c.image_path
                }
                for c in chunks
            ]
            self.vector_store.add_documents(
                tenant_id=tenant_id,
                document_id=doc.id,
                chunks=chunks_payload,
                embeddings=embeddings
            )
            # Step 5: Mark synced
            self.repo.update_chunks_sync_status([c.id for c in chunks], SyncStatus.SYNCED)
            doc.status = IngestionStatus.COMPLETED.value
            self.db.commit()
            self.db.refresh(doc)
            return doc
        except Exception as e:
            logger.error(f"Embedding or vector synchronization failed for doc {doc.id}: {e}")
            self.repo.update_chunks_sync_status([c.id for c in chunks], SyncStatus.FAILED)
            doc.status = IngestionStatus.FAILED.value
            self.db.commit()
            raise e

    def delete_document(self, document_id: str, tenant_id: str) -> bool:
        """
        Deletes document and cascades through relational DB and vector database.
        """
        # 1. Delete points in vector store
        self.vector_store.delete_document(document_id, tenant_id)

        # 2. Delete relational metadata in DB
        return self.repo.delete_document(document_id, tenant_id)

    def reconcile_failed_syncs(self, tenant_id: Optional[str] = None) -> int:
        """
        Reconciliation job: scans DocumentChunks with SyncStatus.FAILED or PENDING
        and re-synchronizes vectors to ensure eventual consistency.
        """
        query = self.db.query(DocumentChunk).filter(DocumentChunk.sync_status != SyncStatus.SYNCED.value)
        if tenant_id:
            query = query.filter(DocumentChunk.tenant_id == tenant_id)

        unsynced_chunks = query.all()
        if not unsynced_chunks:
            return 0

        # Group by document
        docs_map = {}
        for c in unsynced_chunks:
            docs_map.setdefault(c.document_id, []).append(c)

        reconciled_count = 0
        for doc_id, chunks in docs_map.items():
            # FIX WEAK-10: Per-document try/except so one failure doesn't abort all others
            try:
                doc = self.repo.get_document(doc_id)
                if not doc:
                    continue
                embed_texts = [c.summary_text if (c.chunk_type == "table" and c.summary_text) else c.content_text for c in chunks]
                # Batch embedding (FIX WEAK-3 applied here too)
                batch_size = 16
                embeddings = []
                for i in range(0, len(embed_texts), batch_size):
                    batch = embed_texts[i:i+batch_size]
                    batch_embeddings = self.embedding_pipeline.model.encode(batch, show_progress_bar=False).tolist()
                    embeddings.extend(batch_embeddings)
                chunks_payload = [
                    {
                        "id": c.id,
                        "chunk_index": c.chunk_index,
                        "page": c.page_number,
                        "type": c.chunk_type,
                        "text": c.content_text,
                        "summary": c.summary_text,
                        "filename": doc.filename,
                        "source": doc.filename,
                        "image_path": c.image_path
                    }
                    for c in chunks
                ]
                self.vector_store.add_documents(doc.tenant_id, doc.id, chunks_payload, embeddings)
                self.repo.update_chunks_sync_status([c.id for c in chunks], SyncStatus.SYNCED)
                doc.status = IngestionStatus.COMPLETED.value
                reconciled_count += len(chunks)
            except Exception as e:
                logger.error(f"Failed to reconcile doc {doc_id}: {e}")

        self.db.commit()
        return reconciled_count
