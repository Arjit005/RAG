"""
scripts/reconcile_neon_migration.py

Stage E2-D: Post-Migration Reconciliation & Integrity Verification
Performs exhaustive canonical comparisons between SQLite and Neon PostgreSQL.
"""

import os
import sys
import sqlite3
import hashlib
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from qdrant_client import QdrantClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.rag.db.database import normalize_database_url

def main():
    load_dotenv()
    src_db = "rag_enterprise.db"
    mig_url_raw = os.getenv("DATABASE_MIGRATION_URL")
    mig_url = normalize_database_url(mig_url_raw)
    
    sqlite_conn = sqlite3.connect(src_db)
    sqlite_cur = sqlite_conn.cursor()
    engine = create_engine(mig_url)
    
    print("======================================================================")
    print("STAGE E2-D: POST-MIGRATION RECONCILIATION")
    print("======================================================================")
    
    tables = ['tenants', 'users', 'documents', 'document_chunks', 'ingestion_jobs']
    
    with engine.connect() as neon_conn:
        # 1. Row counts comparison
        print("\n[CHECK 1] Row Count Verification:")
        for t in tables:
            sqlite_cur.execute(f"SELECT count(*) FROM {t}")
            src_cnt = sqlite_cur.fetchone()[0]
            neon_cnt = neon_conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            match = "MATCH [PASS]" if src_cnt == neon_cnt else "MISMATCH [FAIL]"
            print(f"  - {t:<16}: SQLite = {src_cnt:<3} | Neon = {neon_cnt:<3} -> {match}")
            if src_cnt != neon_cnt:
                print(f"ERROR: Row count mismatch in table {t}!")
                sys.exit(1)
                
        # 2. Tenants validation
        print("\n[CHECK 2] Tenant Integrity Verification:")
        sqlite_cur.execute("SELECT id, name FROM tenants")
        src_tenants = sqlite_cur.fetchall()
        for t_id, t_name in src_tenants:
            dest = neon_conn.execute(text("SELECT id, name FROM tenants WHERE id = :id"), {"id": t_id}).mappings().first()
            assert dest is not None, f"Tenant {t_id} missing in Neon!"
            assert dest["name"] == t_name, f"Tenant name mismatch for {t_id}!"
            print(f"  - Tenant '{t_id}' ('{t_name}') matched perfectly.")

        # 3. Documents validation
        print("\n[CHECK 3] Document Records & Content Hash Verification:")
        sqlite_cur.execute("SELECT id, tenant_id, filename, file_type, content_hash, page_count, status FROM documents ORDER BY filename")
        src_docs = sqlite_cur.fetchall()
        for d in src_docs:
            d_id, t_id, fname, ftype, chash, pcount, status = d
            dest = neon_conn.execute(text("""
                SELECT id, tenant_id, filename, file_type, content_hash, page_count, status 
                FROM documents WHERE id = :id
            """), {"id": d_id}).mappings().first()
            assert dest is not None, f"Document {d_id} ({fname}) missing in Neon!"
            assert dest["tenant_id"] == t_id, f"tenant_id mismatch on {fname}"
            assert dest["filename"] == fname, f"filename mismatch on {d_id}"
            assert dest["content_hash"] == chash, f"content_hash mismatch on {fname}"
            assert dest["page_count"] == pcount, f"page_count mismatch on {fname}"
            assert dest["status"] == status, f"status mismatch on {fname}"
            print(f"  - Document '{fname}' ({d_id}) | Pages: {pcount} | Hash: {chash[:12]}... [VERIFIED]")

        # 4. Document Chunks validation
        print("\n[CHECK 4] Document Chunks (317 records) Deep Check:")
        sqlite_cur.execute("""
            SELECT id, document_id, tenant_id, chunk_index, page_number, chunk_type, 
                   qdrant_point_id, sync_status, length(content_text)
            FROM document_chunks ORDER BY chunk_index ASC
        """)
        src_chunks = sqlite_cur.fetchall()
        
        neon_chunks_res = neon_conn.execute(text("""
            SELECT id, document_id, tenant_id, chunk_index, page_number, chunk_type, 
                   qdrant_point_id, sync_status, length(content_text) as content_len
            FROM document_chunks
        """)).mappings().all()
        neon_chunk_map = {c["id"]: c for c in neon_chunks_res}
        
        assert len(neon_chunk_map) == 317, f"Expected 317 chunks in Neon, found {len(neon_chunk_map)}"
        
        mismatches = 0
        for sc in src_chunks:
            c_id, doc_id, t_id, c_idx, p_num, c_type, q_id, s_status, text_len = sc
            nc = neon_chunk_map.get(c_id)
            if not nc:
                print(f"  [ERROR] Chunk {c_id} missing in Neon!")
                mismatches += 1
                continue
            if (nc["document_id"] != doc_id or nc["chunk_index"] != c_idx or 
                nc["qdrant_point_id"] != q_id or nc["content_len"] != text_len):
                print(f"  [ERROR] Chunk {c_id} attribute mismatch!")
                mismatches += 1
        
        if mismatches > 0:
            print(f"ERROR: {mismatches} chunk mismatches found!")
            sys.exit(1)
        print("  - All 317 chunks verified: exact IDs, indexes, document links, text lengths, and Qdrant IDs.")

        # 5. Qdrant Cross-Reference Check
        print("\n[CHECK 5] Qdrant Cross-Database Consistency Check:")
        qdrant_path = os.getenv("QDRANT_PATH", "qdrant_storage")
        qdrant_client = QdrantClient(path=qdrant_path)
        points, _ = qdrant_client.scroll(
            collection_name="rag_enterprise_chunks",
            limit=1000,
            with_payload=False,
            with_vectors=False
        )
        qdrant_ids = set(p.id for p in points)
        qdrant_client.close()
        
        neon_chunk_ids = set(neon_chunk_map.keys())
        neon_qdrant_pt_ids = set(c["qdrant_point_id"] for c in neon_chunks_res)
        
        assert len(qdrant_ids) == 317, f"Expected 317 points in Qdrant, got {len(qdrant_ids)}"
        assert neon_chunk_ids == qdrant_ids, "Neon chunk IDs do not match Qdrant point IDs!"
        assert neon_qdrant_pt_ids == qdrant_ids, "Neon qdrant_point_ids do not match Qdrant point IDs!"
        print(f"  - Qdrant points: {len(qdrant_ids)}")
        print(f"  - Neon chunk IDs: {len(neon_chunk_ids)}")
        print(f"  - Discrepancies between Neon and Qdrant: 0 (Exact 1:1 parity)")

        # 6. Foreign key relationship integrity in Neon
        print("\n[CHECK 6] Foreign Key Integrity within Neon PostgreSQL:")
        orphan_chunks = neon_conn.execute(text("""
            SELECT count(*) FROM document_chunks dc
            LEFT JOIN documents d ON dc.document_id = d.id
            WHERE d.id IS NULL
        """)).scalar()
        orphan_docs = neon_conn.execute(text("""
            SELECT count(*) FROM documents d
            LEFT JOIN tenants t ON d.tenant_id = t.id
            WHERE t.id IS NULL
        """)).scalar()
        print(f"  - Orphan document_chunks referencing non-existent documents: {orphan_chunks}")
        print(f"  - Orphan documents referencing non-existent tenants: {orphan_docs}")
        assert orphan_chunks == 0, "Found orphan document_chunks in Neon!"
        assert orphan_docs == 0, "Found orphan documents in Neon!"
        
    sqlite_conn.close()
    print("\n======================================================================")
    print("STAGE E2-D RECONCILIATION RESULT: 100% RECONCILED — ZERO DISCREPANCIES")
    print("======================================================================")

if __name__ == "__main__":
    main()
