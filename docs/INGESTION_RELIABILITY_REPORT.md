# Ingestion & Cross-Store Reliability Report

## 1. Cross-Store Coordination (PostgreSQL & Qdrant)
In an enterprise multi-modal RAG architecture, relational metadata (documents, chunks, tenants) resides in PostgreSQL, while embeddings and payloads reside in Qdrant. Because these systems do not share a single distributed transaction coordinator, partial failure handling is critical:

1. **Deletion Synchronization:**
   - Document deletion operations in `DocumentLifecycleService.delete_document` first query all matching Qdrant points (`tenant_id` + `document_id`).
   - Vectors are deleted from Qdrant via `client.delete(points=...)`.
   - Relational rows in PostgreSQL are deleted in an atomic transaction with foreign key cascade.
   - Deletion is idempotent: retrying a deletion on an already-deleted document returns cleanly without raising errors.
2. **Local Concurrency Protection:**
   - In development environments using local disk-based Qdrant (`./qdrant_storage`), file-level locking via `portalocker` restricts storage access to one process.
   - FastAPI now manages a singleton store via `get_shared_vector_store()`, preventing internal task thread deadlocks.
   - For production multi-worker environments, deploying standalone Qdrant server (`QDRANT_HOST`) eliminates file lock contention completely.

## 2. Ingestion Job Durability & Lifecycle
- Every upload creates an initial `IngestionJob` record in PostgreSQL with status `pending` and `progress_percent: 0`.
- Document processing runs asynchronously via FastAPI `BackgroundTasks`.
- Stage transitions update the database record (`processing` -> `completed` or `failed`), recording error details upon exception.
- State is persistent across page navigation and queryable via `GET /api/pipeline/jobs`.
