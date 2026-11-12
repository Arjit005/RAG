from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from src.rag.db.models import Tenant, User, Document, DocumentChunk, IngestionJob, IngestionStatus, SyncStatus
from src.rag.db.id_generator import generate_document_id, generate_chunk_id, compute_content_hash

class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_default_tenant(self, tenant_id: str = "default-tenant", name: str = "Default Enterprise Org") -> Tenant:
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            tenant = Tenant(id=tenant_id, name=name)
            self.db.add(tenant)
            self.db.commit()
            self.db.refresh(tenant)
        return tenant

    def get_document(self, document_id: str, tenant_id: Optional[str] = None) -> Optional[Document]:
        query = self.db.query(Document).filter(Document.id == document_id)
        if tenant_id:
            query = query.filter(Document.tenant_id == tenant_id)
        return query.first()

    def get_document_by_hash(self, tenant_id: str, content_hash: str) -> Optional[Document]:
        return self.db.query(Document).filter(
            Document.tenant_id == tenant_id,
            Document.content_hash == content_hash
        ).first()

    def list_documents(self, tenant_id: str, limit: int = 100, offset: int = 0) -> List[Document]:
        return self.db.query(Document).filter(
            Document.tenant_id == tenant_id
        ).offset(offset).limit(limit).all()

    def upsert_document(
        self,
        tenant_id: str,
        filename: str,
        file_type: str,
        content_bytes: bytes,
        page_count: int = 1,
        status: IngestionStatus = IngestionStatus.PROCESSING
    ) -> Document:
        content_hash = compute_content_hash(content_bytes)
        doc_id = generate_document_id(tenant_id, filename, content_hash)

        doc = self.get_document(doc_id)
        if doc:
            doc.filename = filename
            doc.file_type = file_type
            doc.page_count = page_count
            doc.status = status.value if isinstance(status, IngestionStatus) else status
        else:
            # Ensure tenant exists
            self.get_or_create_default_tenant(tenant_id)
            doc = Document(
                id=doc_id,
                tenant_id=tenant_id,
                filename=filename,
                file_type=file_type,
                content_hash=content_hash,
                page_count=page_count,
                status=status.value if isinstance(status, IngestionStatus) else status
            )
            self.db.add(doc)

        self.db.commit()
        self.db.refresh(doc)
        return doc

    def save_chunks(
        self,
        document_id: str,
        tenant_id: str,
        chunks_data: List[Dict[str, Any]]
    ) -> List[DocumentChunk]:
        """
        Idempotently writes document chunks. Removes existing chunks for this document if re-indexing.
        """
        # Delete old chunks for this doc to guarantee no duplicates
        self.db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()

        created_chunks = []
        for idx, item in enumerate(chunks_data):
            chunk_type = item.get("type", "text")
            chunk_id = generate_chunk_id(document_id, idx, chunk_type)
            chunk = DocumentChunk(
                id=chunk_id,
                document_id=document_id,
                tenant_id=tenant_id,
                chunk_index=idx,
                page_number=item.get("page", 1),
                chunk_type=chunk_type,
                content_text=item.get("text", ""),
                summary_text=item.get("summary"),
                image_path=item.get("image_path"),
                qdrant_point_id=chunk_id,
                sync_status=SyncStatus.PENDING.value
            )
            self.db.add(chunk)
            created_chunks.append(chunk)

        self.db.commit()
        return created_chunks

    def update_chunks_sync_status(self, chunk_ids: List[str], status: SyncStatus):
        self.db.query(DocumentChunk).filter(
            DocumentChunk.id.in_(chunk_ids)
        ).update({"sync_status": status.value}, synchronize_session=False)
        self.db.commit()

    def delete_document(self, document_id: str, tenant_id: Optional[str] = None) -> bool:
        doc = self.get_document(document_id, tenant_id)
        if not doc:
            return False
        self.db.delete(doc)  # Cascade deletes chunks
        self.db.commit()
        return True
