# API Integration Reference

This document catalogs the complete contract between the Next.js frontend and the FastAPI backend.

---

## 1. Authentication

### `POST /api/auth/token`
Generates a signed HS256 JWT access token.

- **Request Body:**
  ```json
  {
    "email": "admin@enterprise.internal",
    "password": "EnterpriseAdmin2026!"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1Ni...",
    "token_type": "bearer",
    "user_id": "user-admin-default",
    "tenant_id": "default-tenant",
    "email": "admin@enterprise.internal",
    "role": "system_admin"
  }
  ```

---

## 2. Metrics & Telemetry

### `GET /api/metrics/summary`
Returns strictly tenant-scoped metrics from PostgreSQL.
- **Headers:** `Authorization: Bearer <token>`, `X-Tenant-ID: <tenant_id>`
- **Response (200 OK):**
  ```json
  {
    "tenant_id": "default-tenant",
    "total_documents": 6,
    "total_chunks": 317,
    "active_jobs_count": 0,
    "storage_provider": "PostgreSQL (Neon Cloud)",
    "vector_engine": "Qdrant (Local Persistent / FAISS Fallback)"
  }
  ```

### `GET /api/health`
Returns system component liveness.
- **Response (200 OK):**
  ```json
  {
    "status": "healthy",
    "indexed_documents_count": 6,
    "vector_store_ready": true,
    "groq_llm_ready": false,
    "embedding_model": "all-MiniLM-L6-v2"
  }
  ```

---

## 3. Documents & Ingestion

### `GET /api/documents`
Lists documents for the authorized tenant.
- **Query Params:** `limit=100`, `offset=0`, `search=<string>`
- **Response (200 OK):** Array of `DocumentItem`.

### `GET /api/documents/{document_id}`
Returns details for a single authorized document.

### `GET /api/documents/{document_id}/chunks`
Returns all chunks for a document, including `qdrant_point_id` references.

### `POST /api/documents/upload`
Uploads a document for background asynchronous ingestion.
- **Content-Type:** `multipart/form-data`
- **Form Fields:** `file` (Binary content)
- **Validation:** Whitelist (`.pdf`, `.txt`, `.csv`, `.docx`, `.json`), Max 25 MB.
- **Response (200 OK):**
  ```json
  {
    "status": "accepted",
    "job_id": "job-...",
    "filename": "...",
    "tenant_id": "default-tenant",
    "message": "Document accepted for asynchronous ingestion."
  }
  ```

### `DELETE /api/documents/{document_id}`
Idempotently deletes a document from PostgreSQL and associated points from Qdrant.

---

## 4. Research Chat & Streaming

### `POST /api/chat/stream`
Server-Sent Events streaming chat endpoint.
- **Request Body:**
  ```json
  {
    "query": "What is attention?",
    "top_k": 5,
    "use_hybrid": true,
    "use_rerank": true,
    "chat_history": [],
    "model": "qwen/qwen3.6-27b"
  }
  ```
- **SSE Stream Sequence:**
  1. `data: {"type": "message_start", "query": "...", "tenant_id": "..."}`
  2. `data: {"type": "citations", "citations": [...]}`
  3. `data: {"type": "token", "token": "..."}`
  4. `data: {"type": "message_complete"}`
