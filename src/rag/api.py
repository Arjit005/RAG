import os
import sys

# Memory optimizations for constrained environments (e.g., Render Free 512MB RAM)
os.environ["TORCH_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MALLOC_ARENA_MAX"] = "2"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import json
import uuid
import datetime
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Header, Depends, BackgroundTasks, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
import jwt

# Setup sys.path for internal imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.db.database import get_db, SessionLocal
from src.rag.db.models import Document, DocumentChunk, IngestionJob, Tenant, User, UserRole, IngestionStatus
from src.rag.db.repository import DocumentRepository
from src.rag.db.lifecycle import DocumentLifecycleService
from src.rag.db.auth import create_access_token, verify_password
import src.rag.db.auth as auth_service
from src.rag.qdrant_store import QdrantVectorStore
from src.rag.llm.model_router import get_model_router, ProviderType, TierType, CircuitState

# Initialize FastAPI App
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Intelligence Enterprise API",
    description="Production REST API for Document Intelligence, Hybrid Vector Search, and Groq LLM Querying.",
    version="1.0.0"
)

# Mount static web directory
static_dir = Path(__file__).resolve().parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Setup CORS with explicit origin support
env_mode = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
frontend_origin = os.getenv("FRONTEND_URL", "").strip().rstrip("/")

if env_mode in ("production", "prod"):
    # In production, ONLY the configured FRONTEND_URL is allowed.
    # Localhost origins are strictly prohibited in production.
    if frontend_origin:
        allowed_origins = [frontend_origin]
    else:
        allowed_origins = []
else:
    allowed_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
    if frontend_origin:
        allowed_origins.append(frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

from src.rag.vector_store_factory import get_vector_store

# Shared RAG Instance and Centralized Vector Store
rag_engine: Optional[Any] = None

def get_shared_vector_store():
    """
    Returns the centralized vector store instance from vector_store_factory.
    Guarantees that retrieval, ingestion, deletion, and health probes all use the exact same store.
    """
    try:
        return get_vector_store()
    except Exception as e:
        logger.exception(f"Failed to obtain centralized vector store: {e}")
        raise e

def get_rag_engine():
    global rag_engine
    if rag_engine is None:
        try:
            from rag.search import RAGSearch
        except ImportError:
            from search import RAGSearch
        v_store = get_shared_vector_store()
        if v_store is None:
            logger.warning("Vector store is None; RAGSearch will attempt its own store initialization.")
        try:
            rag_engine = RAGSearch(vectorstore=v_store)
        except Exception as e:
            logger.error(f"Failed to initialize RAG engine: {e}")
            raise HTTPException(status_code=503, detail="RAG engine initialization failed.")
    return rag_engine

# --- Security & Authentication Dependencies ---
security = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    user_id: str
    email: str
    tenant_id: str
    role: str


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> AuthenticatedUser:
    """
    Cryptographically authenticates caller identity via signed JWT Bearer token.
    Fails closed with HTTP 401 if credentials are missing, malformed, or expired.
    Validates user existence and tenant membership in PostgreSQL.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials. Bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    try:
        payload = auth_service.decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please authenticate again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token signature or claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    tenant_id: str = payload.get("tenant_id")
    email: str = payload.get("email")
    role: str = payload.get("role", UserRole.MEMBER.value)

    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if not user:
        revoked = db.query(User).filter(User.id == user_id).first()
        if revoked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not authorized for the specified tenant."
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account does not exist or has been revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        tenant_id=user.tenant_id,
        role=user.role
    )


def get_authorized_tenant(
    current_user: AuthenticatedUser = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")
) -> str:
    """
    Resolves the authorized tenant boundary derived from verified user context.
    - If X-Tenant-ID is supplied, it must strictly match current_user.tenant_id (or user must be system_admin).
    - Prevents header-spoofing across tenant boundaries (fails closed with 403 Forbidden).
    """
    if x_tenant_id and x_tenant_id != current_user.tenant_id:
        if current_user.role != UserRole.SYSTEM_ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: User '{current_user.email}' is not a member of tenant '{x_tenant_id}'."
            )
        return x_tenant_id

    return current_user.tenant_id


# Pydantic Request/Response Models
class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    email: str
    role: str

class QueryRequest(BaseModel):
    query: str = Field(..., description="User question or query string", json_schema_extra={"example": "What is attention mechanism?"})
    top_k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    model: str = Field("qwen/qwen3.8-27b", description="Groq LLM model name")
    use_hybrid: bool = Field(True, description="Enable BM25 + FAISS Hybrid Search")
    use_rerank: bool = Field(True, description="Enable FlashRank Cross-Encoder Re-ranking")
    chat_history: Optional[List[Dict[str, Any]]] = Field(default=[], description="Previous conversation history")

class Citation(BaseModel):
    source: str
    page: int
    snippet: str
    distance: float
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    type: Optional[str] = "text"
    image_path: Optional[str] = None

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000, description="User question or query string", json_schema_extra={"example": "What is attention mechanism?"})
    top_k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    model: str = Field("qwen/qwen3.8-27b", description="Groq LLM model name")
    use_hybrid: bool = Field(True, description="Enable BM25 + Vector Hybrid Search")
    use_rerank: bool = Field(True, description="Enable FlashRank Cross-Encoder Re-ranking")
    chat_history: Optional[List[Dict[str, Any]]] = Field(default=[], description="Previous conversation history")

class ChatResponse(BaseModel):
    query: str
    answer: str
    citations: List[Citation]
    model: str
    hybrid_enabled: bool
    rerank_enabled: bool
    tenant_id: str
    selected_model_id: Optional[str] = None
    selected_provider: Optional[str] = None
    failover_occurred: Optional[bool] = False

class QueryResponse(BaseModel):
    query: str
    answer: str
    citations: List[Citation]
    model: str
    hybrid_enabled: bool
    rerank_enabled: bool

class HealthResponse(BaseModel):
    status: str
    indexed_documents_count: int
    vector_store_ready: bool
    groq_llm_ready: bool
    embedding_model: str

class ModelDescriptorSchema(BaseModel):
    provider: str
    model_id: str
    display_name: str
    tier: str
    context_window: int
    max_output_tokens: int
    supports_multimodal: bool
    supports_streaming: bool
    priority: int
    enabled: bool

class ProviderHealthSchema(BaseModel):
    provider: str
    state: str
    failure_count: int
    consecutive_429_count: int
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    cooldown_seconds: float
    has_credentials: bool
    active_key_masked: Optional[str] = None
    available_keys_count: int

class ModelsListResponse(BaseModel):
    models: List[ModelDescriptorSchema]
    providers: List[ProviderHealthSchema]
    active_model_id: str

class ModelConfigUpdateRequest(BaseModel):
    model_id: str
    enabled: Optional[bool] = None
    priority: Optional[int] = None

class DocumentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    filename: str
    file_type: str
    content_hash: str
    page_count: int
    status: str
    chunk_count: int
    created_at: str

class DocumentChunkSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    tenant_id: str
    chunk_index: int
    page_number: int
    chunk_type: str
    content_text: str
    summary_text: Optional[str] = None
    image_path: Optional[str] = None
    qdrant_point_id: Optional[str] = None
    sync_status: str

class MetricsSummaryResponse(BaseModel):
    tenant_id: str
    total_documents: int
    total_chunks: int
    active_jobs_count: int
    storage_provider: str
    vector_engine: str

class IngestionJobSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    document_id: Optional[str] = None
    status: str
    progress_percent: int
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


# --- Background Ingestion Worker ---
def process_document_ingestion_job(
    job_id: str,
    tenant_id: str,
    filename: str,
    file_type: str,
    content_bytes: bytes
):
    """
    Background worker orchestrating extraction, chunking, embedding, and vector synchronization.
    Updates the persistent IngestionJob status and progress atomically.
    """
    db = SessionLocal()
    job = None
    try:
        job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
        if job:
            job.status = IngestionStatus.PROCESSING.value
            job.progress_percent = 20
            job.updated_at = datetime.datetime.utcnow()
            db.commit()

        # Text extraction & chunking using dataloader logic
        raw_chunks = []
        page_count = 1

        if file_type == "txt":
            text = content_bytes.decode("utf-8", errors="ignore")
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            split_texts = splitter.split_text(text)
            if not split_texts and text.strip():
                split_texts = [text.strip()]
            for idx, chunk_str in enumerate(split_texts):
                raw_chunks.append({
                    "text": chunk_str,
                    "page": 1,
                    "type": "text",
                    "summary": None
                })
        elif file_type == "pdf":
            import tempfile, pymupdf
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content_bytes)
                tmp_path = tmp.name
            try:
                doc_pdf = pymupdf.open(tmp_path)
                page_count = len(doc_pdf)
                from langchain_text_splitters import RecursiveCharacterTextSplitter
                splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                for page_num in range(page_count):
                    p_text = doc_pdf[page_num].get_text()
                    if p_text.strip():
                        chunks_for_page = splitter.split_text(p_text)
                        if not chunks_for_page:
                            chunks_for_page = [p_text.strip()]
                        for c_idx, sub_chunk in enumerate(chunks_for_page):
                            raw_chunks.append({
                                "text": sub_chunk,
                                "page": page_num + 1,
                                "type": "text",
                                "summary": None
                            })
                doc_pdf.close()
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        else:
            # Fallback for csv, json, md, etc.
            text = content_bytes.decode("utf-8", errors="ignore")
            raw_chunks.append({
                "text": text[:2000] if text.strip() else f"File: {filename}",
                "page": 1,
                "type": "text",
                "summary": None
            })

        logger.info(f"Chunking completed for {filename}: generated {len(raw_chunks)} chunks.")

        if not raw_chunks:
            raise ValueError(f"No extractable text found in '{filename}'.")

        if job:
            job.progress_percent = 50
            job.updated_at = datetime.datetime.utcnow()
            db.commit()

        # Lifecycle synchronization to DB and Qdrant
        vector_store = get_shared_vector_store()
        lifecycle = DocumentLifecycleService(db, vector_store)
        doc = lifecycle.ingest_document(
            tenant_id=tenant_id,
            filename=filename,
            file_type=file_type,
            content_bytes=content_bytes,
            raw_chunks=raw_chunks,
            page_count=page_count
        )

        if job:
            job.document_id = doc.id
            job.status = IngestionStatus.COMPLETED.value
            job.progress_percent = 100
            job.updated_at = datetime.datetime.utcnow()
            db.commit()

    except Exception as e:
        logger.exception(f"Document ingestion job {job_id} failed: {e}")
        try:
            if not job:
                job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
            if job:
                job.status = IngestionStatus.FAILED.value
                job.error_message = str(e)[:500]
                job.updated_at = datetime.datetime.utcnow()
                db.commit()
        except Exception as commit_err:
            logger.error(f"Failed to record failure status for job {job_id}: {commit_err}")
    finally:
        db.close()


# --- Endpoints ---

@app.get("/", tags=["General"])
def root():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "message": "Welcome to RAG Intelligence Enterprise API 🚀",
        "documentation": "/docs",
        "health": "/api/health"
    }

@app.get("/api/health/live", tags=["General"])
def liveness_probe():
    """
    Lightweight liveness probe for orchestrators (Render / Kubernetes).
    Returns immediately without querying database or loading ML weights.
    """
    return {"status": "live", "service": "rag-intelligence-backend"}

@app.get("/api/debug/qdrant-check", tags=["General"])
def debug_qdrant_check(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Diagnostic endpoint to inspect Qdrant connection error details."""
    raw_url = os.getenv("QDRANT_URL") or os.getenv("QDRANT_ENDPOINT") or "NOT_SET"
    masked_url = raw_url[:30] + "..." if len(raw_url) > 30 else raw_url
    q_key = os.getenv("QDRANT_API_KEY")
    masked_key = f"{q_key[:4]}...{q_key[-4:]}" if q_key and len(q_key) > 8 else ("SET" if q_key else "NOT_SET")

    err_detail = None
    collection_status = None
    try:
        q_store = get_shared_vector_store()
        if not q_store:
            err_detail = "get_shared_vector_store returned None"
        elif not hasattr(q_store, "client"):
            err_detail = f"q_store has no client attribute: {type(q_store)}"
        else:
            q_coll = os.getenv("QDRANT_COLLECTION", "rag_enterprise_chunks")
            c = q_store.client.get_collection(q_coll)
            collection_status = str(c.status)
    except Exception as e:
        err_detail = f"{type(e).__name__}: {str(e)}"

    return {
        "configured_url_prefix": masked_url,
        "api_key_status": masked_key,
        "error": err_detail,
        "collection_status": collection_status
    }

@app.get("/api/health", response_model=HealthResponse, tags=["General"])
def health_check(db: Session = Depends(get_db)):
    """
    Comprehensive readiness check inspecting real infrastructure:
    - Neon PostgreSQL connection
    - Qdrant Vector Store readiness
    - Model router availability
    Fails with 503 if critical dependencies are down.
    """
    # 1. Check Neon PostgreSQL
    db_healthy = False
    try:
        from sqlalchemy import text
        val = db.execute(text("SELECT 1;")).scalar()
        db_healthy = (val == 1)
    except Exception as e:
        logger.error(f"Health probe database error: {e}")
        db_healthy = False

    # 2. Check Qdrant Vector Store
    vector_store_healthy = False
    q_store = get_shared_vector_store()
    if q_store and hasattr(q_store, "client"):
        try:
            q_coll = os.getenv("QDRANT_COLLECTION", "rag_enterprise_chunks")
            q_store.client.get_collection(q_coll)
            vector_store_healthy = True
        except Exception as e:
            logger.error(f"Health probe Qdrant error: {e}")
            vector_store_healthy = False

    # 3. Model Router Status
    router = get_model_router()
    models = router.registry
    active_models_count = len([m for m in models if m.enabled and router.health_map.get(m.provider) and router.health_map[m.provider].state != CircuitState.OPEN])

    # Readiness check strictly fails if vector store OR database is not healthy
    is_overall_healthy = db_healthy and vector_store_healthy

    if not is_overall_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "degraded",
                "database_ready": db_healthy,
                "vector_store_ready": vector_store_healthy,
                "active_models_count": active_models_count
            }
        )

    return {
        "status": "healthy",
        "indexed_documents_count": db.query(Document).count() if db_healthy else 0,
        "vector_store_ready": vector_store_healthy,
        "groq_llm_ready": active_models_count > 0,
        "embedding_model": os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    }

# --- Authentication Endpoints ---

@app.post("/api/auth/token", response_model=TokenResponse, tags=["Authentication"])
def login_for_access_token(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticates a user by email and password, returning a signed JWT access token.
    """
    try:
        user = db.query(User).filter(User.email == req.email).first()
    except Exception as db_err:
        logger.exception("Database query failed during login")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database connection error: {str(db_err)}"
        )

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token = create_access_token(
            user_id=user.id,
            email=user.email,
            tenant_id=user.tenant_id,
            role=user.role
        )
    except Exception as token_err:
        logger.exception("Token generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"JWT creation failed: {str(token_err)}"
        )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "role": user.role
    }

@app.get("/api/auth/me", tags=["Authentication"])
def get_auth_me(current_user: AuthenticatedUser = Depends(get_current_user)):
    """
    Returns verified user context for the active session.
    Used by frontend session guards and profile headers.
    """
    return {
        "authenticated": True,
        "user_id": current_user.user_id,
        "email": current_user.email,
        "tenant_id": current_user.tenant_id,
        "role": current_user.role
    }


# --- Authenticated Document Management & Ingestion (Phase F4) ---

@app.get("/api/documents", response_model=List[DocumentSchema], tags=["Documents"])
def list_documents(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Filter by filename"),
    tenant_id: str = Depends(get_authorized_tenant),
    db: Session = Depends(get_db)
):
    """
    Returns authentic document records belonging to the authorized tenant from PostgreSQL.
    Supports optional search filter and pagination.
    """
    query = db.query(Document).filter(Document.tenant_id == tenant_id)
    if search:
        query = query.filter(Document.filename.ilike(f"%{search}%"))
    
    docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()
    
    results = []
    for d in docs:
        chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == d.id).count()
        results.append({
            "id": d.id,
            "tenant_id": d.tenant_id,
            "filename": d.filename,
            "file_type": d.file_type,
            "content_hash": d.content_hash,
            "page_count": d.page_count,
            "status": d.status,
            "chunk_count": chunk_count,
            "created_at": d.created_at.isoformat() if d.created_at else ""
        })
    return results

@app.get("/api/documents/{document_id}", response_model=DocumentSchema, tags=["Documents"])
def get_document(
    document_id: str,
    tenant_id: str = Depends(get_authorized_tenant),
    db: Session = Depends(get_db)
):
    """
    Returns metadata for a specific document belonging to the authorized tenant.
    """
    repo = DocumentRepository(db)
    doc = repo.get_document(document_id, tenant_id=tenant_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found."
        )
    chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count()
    return {
        "id": doc.id,
        "tenant_id": doc.tenant_id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "content_hash": doc.content_hash,
        "page_count": doc.page_count,
        "status": doc.status,
        "chunk_count": chunk_count,
        "created_at": doc.created_at.isoformat() if doc.created_at else ""
    }

@app.get("/api/documents/{document_id}/chunks", response_model=List[DocumentChunkSchema], tags=["Documents"])
def get_document_chunks(
    document_id: str,
    tenant_id: str = Depends(get_authorized_tenant),
    db: Session = Depends(get_db)
):
    """
    Returns chunks belonging to an authorized document. Fails closed with 404 if not found or cross-tenant.
    """
    repo = DocumentRepository(db)
    doc = repo.get_document(document_id, tenant_id=tenant_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for tenant '{tenant_id}'."
        )
    
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id,
        DocumentChunk.tenant_id == tenant_id
    ).order_by(DocumentChunk.chunk_index.asc()).all()
    
    return chunks

@app.delete("/api/documents/{document_id}", tags=["Documents"])
def delete_document(
    document_id: str,
    tenant_id: str = Depends(get_authorized_tenant),
    db: Session = Depends(get_db)
):
    """
    Idempotently and atomically deletes a document from PostgreSQL and associated vectors from Qdrant.
    Enforces tenant authorization boundary.
    """
    repo = DocumentRepository(db)
    doc = repo.get_document(document_id, tenant_id=tenant_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for tenant '{tenant_id}'."
        )

    vector_store = get_shared_vector_store()
    if vector_store:
        lifecycle = DocumentLifecycleService(db, vector_store)
        success = lifecycle.delete_document(document_id, tenant_id=tenant_id)
    else:
        # Vector store unavailable / locked: fall back to repository cascade delete in DB
        repo.delete_document(document_id, tenant_id=tenant_id)
        success = True
    
    return {
        "status": "deleted",
        "document_id": document_id,
        "tenant_id": tenant_id,
        "success": success
    }

@app.post("/api/documents/upload", tags=["Documents"])
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_authorized_tenant),
    db: Session = Depends(get_db)
):
    """
    Authenticated document upload with file validation and background ingestion scheduling.
    Prevents UI freezing and persists IngestionJob tracking.
    """
    ALLOWED_EXTENSIONS = {".pdf", ".txt", ".csv", ".docx", ".json"}
    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB limit

    # FIX WEAK-15: Early rejection using Content-Length header before reading into RAM
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds maximum allowed size of 25MB.")

    # Path traversal and filename sanitization
    safe_filename = Path(file.filename).name
    ext = Path(safe_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of 25MB."
        )

    # Register initial IngestionJob record
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    job = IngestionJob(
        id=job_id,
        tenant_id=tenant_id,
        status=IngestionStatus.PENDING.value,
        progress_percent=0
    )
    db.add(job)
    db.commit()

    # Schedule background processing
    file_type = ext.lstrip(".")
    background_tasks.add_task(
        process_document_ingestion_job,
        job_id=job_id,
        tenant_id=tenant_id,
        filename=safe_filename,
        file_type=file_type,
        content_bytes=content
    )

    return {
        "status": "accepted",
        "job_id": job_id,
        "filename": safe_filename,
        "tenant_id": tenant_id,
        "message": "Document accepted for asynchronous ingestion."
    }

@app.get("/api/metrics/summary", response_model=MetricsSummaryResponse, tags=["Metrics"])
def get_metrics_summary(
    tenant_id: str = Depends(get_authorized_tenant),
    db: Session = Depends(get_db)
):
    """
    Returns authentic, strictly tenant-scoped metrics from PostgreSQL.
    Global tenant count is redacted from ordinary tenant responses.
    """
    total_docs = db.query(Document).filter(Document.tenant_id == tenant_id).count()
    total_chunks = db.query(DocumentChunk).filter(DocumentChunk.tenant_id == tenant_id).count()
    active_jobs = db.query(IngestionJob).filter(
        IngestionJob.tenant_id == tenant_id,
        IngestionJob.status.in_(["pending", "processing"])
    ).count()

    return {
        "tenant_id": tenant_id,
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "active_jobs_count": active_jobs,
        "storage_provider": "PostgreSQL (Neon Cloud)",
        "vector_engine": "Qdrant (Local Persistent / FAISS Fallback)"
    }

@app.get("/api/pipeline/jobs", response_model=List[IngestionJobSchema], tags=["Pipeline"])
def list_pipeline_jobs(
    limit: int = Query(50, ge=1, le=200),
    tenant_id: str = Depends(get_authorized_tenant),
    db: Session = Depends(get_db)
):
    """
    Returns persisted ingestion job records for the authorized tenant.
    """
    jobs = db.query(IngestionJob).filter(
        IngestionJob.tenant_id == tenant_id
    ).order_by(IngestionJob.created_at.desc()).limit(limit).all()

    results = []
    for j in jobs:
        results.append({
            "id": j.id,
            "tenant_id": j.tenant_id,
            "document_id": j.document_id,
            "status": j.status,
            "progress_percent": j.progress_percent,
            "error_message": j.error_message,
            "created_at": j.created_at.isoformat() if j.created_at else "",
            "updated_at": j.updated_at.isoformat() if j.updated_at else ""
        })
    return results

# --- Authenticated Research Chat Endpoints (Phase F5) ---

@app.post("/api/chat", response_model=ChatResponse, tags=["Research Chat"])
def chat_authenticated(
    req: ChatRequest,
    tenant_id: str = Depends(get_authorized_tenant)
):
    """
    Authenticated research chat endpoint enforcing strict tenant isolation.
    Executes hybrid retrieval, optional cross-encoder reranking, and evidence-grounded synthesis.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty or whitespace.")

    engine = get_rag_engine()
    if req.model != engine.llm_model:
        engine.llm_model = req.model
        engine.init_llm()

    try:
        res = engine.search_and_answer(
            query=req.query,
            top_k=req.top_k,
            chat_history=req.chat_history,
            use_hybrid=req.use_hybrid,
            use_rerank=req.use_rerank,
            tenant_id=tenant_id
        )

        # Ensure all citation fields are strictly string serialized for Pydantic
        clean_citations = []
        for c in res.get("citations", []):
            clean_citations.append({
                "source": str(c.get("source", "Unknown")),
                "page": int(c.get("page", 1)),
                "snippet": str(c.get("snippet", "")),
                "distance": float(c.get("distance", 0.0)),
                "document_id": str(c.get("document_id")) if c.get("document_id") is not None else None,
                "chunk_id": str(c.get("chunk_id")) if c.get("chunk_id") is not None else None,
                "type": str(c.get("type", "text")),
                "image_path": str(c.get("image_path")) if c.get("image_path") else None
            })

        return {
            "query": req.query,
            "answer": res["answer"],
            "citations": clean_citations,
            "model": req.model,
            "hybrid_enabled": req.use_hybrid,
            "rerank_enabled": req.use_rerank,
            "tenant_id": tenant_id,
            "selected_model_id": res.get("model_id", req.model),
            "selected_provider": res.get("provider", "unknown"),
            "failover_occurred": res.get("failover_occurred", False)
        }
    except Exception as e:
        logger.error(f"Error in chat_authenticated: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while executing the research inquiry.")


@app.post("/api/chat/stream", tags=["Research Chat"])
def chat_stream_authenticated(
    req: ChatRequest,
    tenant_id: str = Depends(get_authorized_tenant)
):
    """
    Authenticated Server-Sent Events (SSE) streaming endpoint for Research Chat.
    Emits structured events:
      - {"type": "message_start", "query": "..."}
      - {"type": "citations", "citations": [...]}
      - {"type": "token", "token": "..."}
      - {"type": "message_complete"}
      - {"type": "error", "error": "..."}
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty or whitespace.")

    engine = get_rag_engine()
    if req.model != engine.llm_model:
        engine.llm_model = req.model
        engine.init_llm()

    def sse_event_generator():
        try:
            # 1. Message start event
            yield f"data: {json.dumps({'type': 'message_start', 'query': req.query, 'tenant_id': tenant_id})}\n\n"

            # 2. Stream citations and tokens from engine
            for event in engine.stream_and_answer(
                query=req.query,
                top_k=req.top_k,
                chat_history=req.chat_history,
                use_hybrid=req.use_hybrid,
                use_rerank=req.use_rerank,
                tenant_id=tenant_id
            ):
                event_type = event.get("type")
                if event_type == "done":
                    yield f"data: {json.dumps({'type': 'message_complete'})}\n\n"
                elif event_type == "citations":
                    clean_citations = []
                    for c in event.get("citations", []):
                        clean_citations.append({
                            "source": str(c.get("source", "Unknown")),
                            "page": int(c.get("page", 1)),
                            "snippet": str(c.get("snippet", "")),
                            "distance": float(c.get("distance", 0.0)),
                            "document_id": str(c.get("document_id")) if c.get("document_id") is not None else None,
                            "chunk_id": str(c.get("chunk_id")) if c.get("chunk_id") is not None else None,
                            "type": str(c.get("type", "text")),
                            "image_path": str(c.get("image_path")) if c.get("image_path") else None
                        })
                    yield f"data: {json.dumps({'type': 'citations', 'citations': clean_citations})}\n\n"
                elif event_type == "token":
                    yield f"data: {json.dumps(event)}\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"

        except Exception as e:
            logger.error(f"Error in chat_stream_authenticated SSE generator: {e}")
            err_payload = {"type": "error", "error": "Inquiry synthesis interrupted or failed."}
            yield f"data: {json.dumps(err_payload)}\n\n"

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# --- Multi-Provider LLM Router Endpoints ---

@app.get("/api/llm/models", response_model=ModelsListResponse, tags=["LLM Model Router"])
def get_llm_models(tenant_id: str = Depends(get_authorized_tenant)):
    """
    Returns registered models, provider circuit breaker health, tier classification,
    and masked credentials status.
    """
    router = get_model_router()
    models_out = []
    for m in router.registry:
        models_out.append(ModelDescriptorSchema(
            provider=m.provider.value,
            model_id=m.model_id,
            display_name=m.display_name,
            tier=m.tier.value,
            context_window=m.context_window,
            max_output_tokens=m.max_output_tokens,
            supports_multimodal=m.supports_multimodal,
            supports_streaming=m.supports_streaming,
            priority=m.priority,
            enabled=m.enabled
        ))

    providers_out = []
    for p in ProviderType:
        health = router.health_map[p]
        keys = router.get_provider_keys(p)
        active_key = router.get_active_key(p)
        masked = None
        if active_key:
            masked = f"{active_key[:4]}...{active_key[-4:]}" if len(active_key) > 8 else "***"

        providers_out.append(ProviderHealthSchema(
            provider=p.value,
            state=health.state.value,
            failure_count=health.failure_count,
            consecutive_429_count=health.consecutive_429_count,
            last_failure_time=health.last_failure_time,
            last_success_time=health.last_success_time,
            cooldown_seconds=health.cooldown_seconds,
            has_credentials=len(keys) > 0,
            active_key_masked=masked,
            available_keys_count=len(keys)
        ))

    engine = get_rag_engine()
    return ModelsListResponse(
        models=models_out,
        providers=providers_out,
        active_model_id=engine.llm_model
    )


@app.post("/api/llm/config", tags=["LLM Model Router"])
def update_llm_model_config(
    req: ModelConfigUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Allows system administrators to enable/disable specific models or update priorities.
    Restricted to system administrators to prevent cross-tenant disruption.
    """
    if current_user.role not in (UserRole.SYSTEM_ADMIN.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only system administrators can update global LLM model configuration."
        )

    router = get_model_router()
    target_model = None
    for m in router.registry:
        if m.model_id == req.model_id:
            target_model = m
            break

    if not target_model:
        raise HTTPException(status_code=404, detail=f"Model '{req.model_id}' not found in registry.")

    if req.enabled is not None:
        target_model.enabled = req.enabled
    if req.priority is not None:
        target_model.priority = req.priority

    return {
        "status": "success",
        "message": f"Updated model configuration for {req.model_id}",
        "model_id": target_model.model_id,
        "enabled": target_model.enabled,
        "priority": target_model.priority
    }


# --- Query & Legacy Upload Endpoints ---

@app.post("/api/query", response_model=QueryResponse, tags=["RAG Search"])
def query_rag(req: QueryRequest):
    engine = get_rag_engine()
    if req.model != engine.llm_model:
        engine.llm_model = req.model
        engine.init_llm()
        
    try:
        res = engine.search_and_answer(
            query=req.query,
            top_k=req.top_k,
            chat_history=req.chat_history,
            use_hybrid=req.use_hybrid,
            use_rerank=req.use_rerank
        )
        
        return {
            "query": req.query,
            "answer": res["answer"],
            "citations": res["citations"],
            "model": req.model,
            "hybrid_enabled": req.use_hybrid,
            "rerank_enabled": req.use_rerank
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing RAG search: {str(e)}")

@app.post("/api/query/stream", tags=["RAG Search"])
def query_rag_stream(req: QueryRequest):
    engine = get_rag_engine()
    if req.model != engine.llm_model:
        engine.llm_model = req.model
        engine.init_llm()

    def event_generator():
        try:
            for event in engine.stream_and_answer(
                query=req.query,
                top_k=req.top_k,
                chat_history=req.chat_history,
                use_hybrid=req.use_hybrid,
                use_rerank=req.use_rerank
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            err_event = {"type": "error", "error": str(e)}
            yield f"data: {json.dumps(err_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
