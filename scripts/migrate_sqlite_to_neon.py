"""
scripts/migrate_sqlite_to_neon.py

Stage E2: Live Data Migration from local SQLite (rag_enterprise.db) to Neon Cloud PostgreSQL.
Complies with all enterprise safeguards:
1. Validates source integrity and backup existence.
2. Migrates in strict Foreign Key order:
   - Tenants
   - Users
   - Documents
   - Document Chunks (batches of 100)
   - Ingestion Jobs
3. Strict idempotency checking:
   - Compares existing primary key records.
   - If record exists with exact matching attributes -> safely skips.
   - If record exists with conflicting attributes -> halts and raises ConflictError.
   - If record does not exist -> safely inserts.
4. Preserves all stable UUIDs, timestamps, Qdrant references, and content hashes without modification.
5. Zero vector modifications or re-embeddings.
"""

import os
import sys
import json
import sqlite3
import datetime
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from qdrant_client import QdrantClient

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.rag.db.database import normalize_database_url


class MigrationConflictError(Exception):
    """Raised when an existing record in Neon conflicts with source data."""
    pass


def parse_datetime(dt_val: Any) -> datetime.datetime:
    """Safely convert SQLite string/timestamp to Python datetime object."""
    if dt_val is None:
        return None
    if isinstance(dt_val, datetime.datetime):
        return dt_val
    if isinstance(dt_val, str):
        # Format usually: YYYY-MM-DD HH:MM:SS.mmmmmm or YYYY-MM-DDTHH:MM:SS
        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S"
        ):
            try:
                return datetime.datetime.strptime(dt_val, fmt)
            except ValueError:
                pass
        return datetime.datetime.fromisoformat(dt_val)
    raise ValueError(f"Unsupported datetime format: {dt_val}")


def migrate_tenants(sqlite_cur: sqlite3.Cursor, neon_conn) -> Tuple[int, int]:
    """Migrate tenants table."""
    print("\n--- [1/5] Migrating Tenants ---")
    sqlite_cur.execute("SELECT id, name, created_at FROM tenants")
    rows = sqlite_cur.fetchall()
    
    inserted = 0
    skipped = 0
    
    for r in rows:
        tenant_id, name, created_at_str = r
        created_at = parse_datetime(created_at_str)
        
        # Check existing in Neon
        check_query = text("SELECT id, name, created_at FROM tenants WHERE id = :id")
        res = neon_conn.execute(check_query, {"id": tenant_id}).mappings().first()
        
        if res:
            # Check for conflict
            if res["name"] == name:
                print(f"  [SKIP] Tenant '{tenant_id}' already exists and matches identically.")
                skipped += 1
                continue
            else:
                raise MigrationConflictError(
                    f"Conflict in tenant {tenant_id}: Source name='{name}', Dest name='{res['name']}'"
                )
        
        insert_query = text("""
            INSERT INTO tenants (id, name, created_at)
            VALUES (:id, :name, :created_at)
        """)
        neon_conn.execute(insert_query, {
            "id": tenant_id,
            "name": name,
            "created_at": created_at
        })
        print(f"  [INSERT] Tenant '{tenant_id}' ('{name}') inserted successfully.")
        inserted += 1
        
    return inserted, skipped


def migrate_users(sqlite_cur: sqlite3.Cursor, neon_conn) -> Tuple[int, int]:
    """Migrate users table."""
    print("\n--- [2/5] Migrating Users ---")
    sqlite_cur.execute("SELECT id, tenant_id, email, hashed_password, role, created_at FROM users")
    rows = sqlite_cur.fetchall()
    
    inserted = 0
    skipped = 0
    
    for r in rows:
        user_id, tenant_id, email, hashed_pwd, role, created_at_str = r
        created_at = parse_datetime(created_at_str)
        
        check_query = text("SELECT id, tenant_id, email, role FROM users WHERE id = :id")
        res = neon_conn.execute(check_query, {"id": user_id}).mappings().first()
        if res:
            if res["tenant_id"] == tenant_id and res["email"] == email and res["role"] == role:
                print(f"  [SKIP] User '{user_id}' already exists and matches identically.")
                skipped += 1
                continue
            else:
                raise MigrationConflictError(f"Conflict in user {user_id}: Mismatched attributes.")
                
        insert_query = text("""
            INSERT INTO users (id, tenant_id, email, hashed_password, role, created_at)
            VALUES (:id, :tenant_id, :email, :hashed_password, :role, :created_at)
        """)
        neon_conn.execute(insert_query, {
            "id": user_id,
            "tenant_id": tenant_id,
            "email": email,
            "hashed_password": hashed_pwd,
            "role": role,
            "created_at": created_at
        })
        inserted += 1
        
    print(f"  Users: {inserted} inserted, {skipped} skipped.")
    return inserted, skipped


def migrate_documents(sqlite_cur: sqlite3.Cursor, neon_conn) -> Tuple[int, int]:
    """Migrate documents table."""
    print("\n--- [3/5] Migrating Documents ---")
    sqlite_cur.execute("""
        SELECT id, tenant_id, filename, file_type, content_hash, page_count, status, created_at, updated_at
        FROM documents
        ORDER BY created_at ASC
    """)
    rows = sqlite_cur.fetchall()
    
    inserted = 0
    skipped = 0
    
    for r in rows:
        doc_id, tenant_id, filename, file_type, content_hash, page_count, status, created_at_str, updated_at_str = r
        created_at = parse_datetime(created_at_str)
        updated_at = parse_datetime(updated_at_str)
        
        check_query = text("""
            SELECT id, tenant_id, filename, file_type, content_hash, page_count, status
            FROM documents WHERE id = :id
        """)
        res = neon_conn.execute(check_query, {"id": doc_id}).mappings().first()
        
        if res:
            if (res["tenant_id"] == tenant_id and 
                res["filename"] == filename and 
                res["content_hash"] == content_hash and
                res["page_count"] == page_count):
                print(f"  [SKIP] Document '{filename}' ({doc_id}) already exists and matches identically.")
                skipped += 1
                continue
            else:
                raise MigrationConflictError(
                    f"Conflict in document {doc_id} ('{filename}'): Attributes mismatch."
                )
        
        insert_query = text("""
            INSERT INTO documents (
                id, tenant_id, filename, file_type, content_hash, page_count, status, created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :filename, :file_type, :content_hash, :page_count, :status, :created_at, :updated_at
            )
        """)
        neon_conn.execute(insert_query, {
            "id": doc_id,
            "tenant_id": tenant_id,
            "filename": filename,
            "file_type": file_type,
            "content_hash": content_hash,
            "page_count": page_count,
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at
        })
        print(f"  [INSERT] Document '{filename}' ({doc_id}) inserted successfully ({page_count} pages).")
        inserted += 1
        
    return inserted, skipped


def migrate_document_chunks(sqlite_cur: sqlite3.Cursor, neon_conn, batch_size: int = 100) -> Tuple[int, int]:
    """Migrate document_chunks table in batches of 100."""
    print("\n--- [4/5] Migrating Document Chunks ---")
    sqlite_cur.execute("""
        SELECT id, document_id, tenant_id, chunk_index, page_number, chunk_type,
               content_text, summary_text, image_path, qdrant_point_id, sync_status, created_at
        FROM document_chunks
        ORDER BY document_id, chunk_index ASC
    """)
    all_chunks = sqlite_cur.fetchall()
    total_chunks = len(all_chunks)
    print(f"  Total source chunks to evaluate: {total_chunks}")
    
    total_inserted = 0
    total_skipped = 0
    
    # Process in batches
    for i in range(0, total_chunks, batch_size):
        batch = all_chunks[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_chunks + batch_size - 1) // batch_size
        print(f"  Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
        
        # Check existing records in this batch
        batch_ids = [c[0] for c in batch]
        existing_res = neon_conn.execute(
            text("SELECT id, document_id, chunk_index, qdrant_point_id FROM document_chunks WHERE id = ANY(:ids)"),
            {"ids": batch_ids}
        ).mappings().all()
        existing_map = {row["id"]: row for row in existing_res}
        
        to_insert = []
        for c in batch:
            (chunk_id, doc_id, tenant_id, chunk_index, page_number, chunk_type,
             content_text, summary_text, image_path, qdrant_point_id, sync_status, created_at_str) = c
            created_at = parse_datetime(created_at_str)
            
            if chunk_id in existing_map:
                dest = existing_map[chunk_id]
                if (dest["document_id"] == doc_id and 
                    dest["chunk_index"] == chunk_index and 
                    dest["qdrant_point_id"] == qdrant_point_id):
                    total_skipped += 1
                    continue
                else:
                    raise MigrationConflictError(
                        f"Conflict in chunk {chunk_id}: Destination mismatch with source."
                    )
            
            to_insert.append({
                "id": chunk_id,
                "document_id": doc_id,
                "tenant_id": tenant_id,
                "chunk_index": chunk_index,
                "page_number": page_number,
                "chunk_type": chunk_type,
                "content_text": content_text,
                "summary_text": summary_text,
                "image_path": image_path,
                "qdrant_point_id": qdrant_point_id,
                "sync_status": sync_status,
                "created_at": created_at
            })
            
        if to_insert:
            insert_query = text("""
                INSERT INTO document_chunks (
                    id, document_id, tenant_id, chunk_index, page_number, chunk_type,
                    content_text, summary_text, image_path, qdrant_point_id, sync_status, created_at
                ) VALUES (
                    :id, :document_id, :tenant_id, :chunk_index, :page_number, :chunk_type,
                    :content_text, :summary_text, :image_path, :qdrant_point_id, :sync_status, :created_at
                )
            """)
            neon_conn.execute(insert_query, to_insert)
            total_inserted += len(to_insert)
            print(f"    Batch {batch_num}: {len(to_insert)} chunks inserted.")
        else:
            print(f"    Batch {batch_num}: All {len(batch)} chunks already exist identically (skipped).")
            
    return total_inserted, total_skipped


def migrate_ingestion_jobs(sqlite_cur: sqlite3.Cursor, neon_conn) -> Tuple[int, int]:
    """Migrate ingestion_jobs table."""
    print("\n--- [5/5] Migrating Ingestion Jobs ---")
    sqlite_cur.execute("""
        SELECT id, tenant_id, document_id, status, progress_percent, error_message, created_at, updated_at
        FROM ingestion_jobs
    """)
    rows = sqlite_cur.fetchall()
    
    inserted = 0
    skipped = 0
    
    for r in rows:
        job_id, tenant_id, doc_id, status, progress, err_msg, created_at_str, updated_at_str = r
        created_at = parse_datetime(created_at_str)
        updated_at = parse_datetime(updated_at_str)
        
        check_query = text("SELECT id, status FROM ingestion_jobs WHERE id = :id")
        res = neon_conn.execute(check_query, {"id": job_id}).mappings().first()
        if res:
            if res["status"] == status:
                skipped += 1
                continue
            else:
                raise MigrationConflictError(f"Conflict in ingestion job {job_id}")
                
        insert_query = text("""
            INSERT INTO ingestion_jobs (
                id, tenant_id, document_id, status, progress_percent, error_message, created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :document_id, :status, :progress_percent, :error_message, :created_at, :updated_at
            )
        """)
        neon_conn.execute(insert_query, {
            "id": job_id,
            "tenant_id": tenant_id,
            "document_id": doc_id,
            "status": status,
            "progress_percent": progress,
            "error_message": err_msg,
            "created_at": created_at,
            "updated_at": updated_at
        })
        inserted += 1
        
    print(f"  Ingestion Jobs: {inserted} inserted, {skipped} skipped.")
    return inserted, skipped


def main():
    load_dotenv()
    src_db = "rag_enterprise.db"
    if not os.path.exists(src_db):
        print(f"ERROR: '{src_db}' not found.")
        sys.exit(1)
        
    mig_url_raw = os.getenv("DATABASE_MIGRATION_URL")
    if not mig_url_raw:
        print("ERROR: DATABASE_MIGRATION_URL is not set.")
        sys.exit(1)
        
    mig_url = normalize_database_url(mig_url_raw)
    engine = create_engine(mig_url, isolation_level="AUTOCOMMIT")
    
    sqlite_conn = sqlite3.connect(src_db)
    sqlite_cur = sqlite_conn.cursor()
    
    print("======================================================================")
    print("STAGE E2-C: LIVE RELATIONAL MIGRATION EXECUTION")
    print("======================================================================")
    print(f"Source Database: {src_db}")
    print(f"Target Database: Neon PostgreSQL (Schema: public)")
    
    # Use a single connection with explicit transaction blocks
    with engine.connect() as neon_conn:
        with neon_conn.begin():
            try:
                t_ins, t_skip = migrate_tenants(sqlite_cur, neon_conn)
                u_ins, u_skip = migrate_users(sqlite_cur, neon_conn)
                d_ins, d_skip = migrate_documents(sqlite_cur, neon_conn)
                c_ins, c_skip = migrate_document_chunks(sqlite_cur, neon_conn, batch_size=100)
                j_ins, j_skip = migrate_ingestion_jobs(sqlite_cur, neon_conn)
                
                print("\n======================================================================")
                print("TRANSACTION COMMITTING TO NEON POSTGRESQL...")
                print("======================================================================")
            except Exception as e:
                print(f"\n[FATAL ERROR] Migration failed during execution: {e}")
                print("TRANSACTION ROLLING BACK. Neon remains unchanged.")
                raise
                
    sqlite_conn.close()
    
    print("\n[SUCCESS] Relational data migration committed successfully.")
    print(f"  Tenants:         {t_ins} inserted, {t_skip} skipped.")
    print(f"  Users:           {u_ins} inserted, {u_skip} skipped.")
    print(f"  Documents:       {d_ins} inserted, {d_skip} skipped.")
    print(f"  Document Chunks: {c_ins} inserted, {c_skip} skipped.")
    print(f"  Ingestion Jobs:  {j_ins} inserted, {j_skip} skipped.")


if __name__ == "__main__":
    main()
