import uuid
import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    Enum,
    Index
)
from sqlalchemy.orm import relationship
import enum
from src.rag.db.database import Base

class UserRole(str, enum.Enum):
    SYSTEM_ADMIN = "system_admin"
    ORG_ADMIN = "org_admin"
    MEMBER = "member"
    VIEWER = "viewer"

class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ChunkType(str, enum.Enum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"

class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="tenant", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)
    role = Column(String(32), default=UserRole.MEMBER.value, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="users")

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True)  # Deterministic UUID or SHA256 string
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(32), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    page_count = Column(Integer, default=1, nullable=False)
    status = Column(String(32), default=IngestionStatus.PENDING.value, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_doc_tenant_content_hash", "tenant_id", "content_hash"),
    )

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String(64), primary_key=True)  # Deterministic UUID
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, default=1, nullable=False)
    chunk_type = Column(String(32), default=ChunkType.TEXT.value, nullable=False)
    content_text = Column(Text, nullable=False)
    summary_text = Column(Text, nullable=True)
    image_path = Column(String(512), nullable=True)
    qdrant_point_id = Column(String(64), nullable=True, index=True)
    sync_status = Column(String(32), default=SyncStatus.PENDING.value, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunk_doc_idx", "document_id", "chunk_index"),
    )

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    document_id = Column(String(64), nullable=True, index=True)
    status = Column(String(32), default=IngestionStatus.PENDING.value, nullable=False)
    progress_percent = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
