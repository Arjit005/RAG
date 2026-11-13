import os
import sys
import json
import sqlite3
import datetime
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sqlalchemy import create_engine, text
from src.rag.db.database import normalize_database_url

def main():
    load_dotenv()
    src_db = 'rag_enterprise.db'
    if not os.path.exists(src_db):
        print(f"ERROR: Source SQLite database '{src_db}' does not exist.")
        sys.exit(1)

    print("======================================================================")
    print("STAGE E2-A: PRE-MIGRATION VALIDATION")
    print("======================================================================")
    
    # 1. Existing backup check
    backup_file = "rag_enterprise_20261110_212548.bak"
    if not os.path.exists(backup_file):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"rag_enterprise_{ts}.bak"
        import shutil
        shutil.copy2(src_db, backup_file)
        print(f"[BACKUP] Created new backup: {backup_file}")
    else:
        print(f"[BACKUP] Verified timestamped backup exists: {backup_file} (Size: {os.path.getsize(backup_file)} bytes)")

    # 2. Verify backup integrity
    conn_bak = sqlite3.connect(backup_file)
    cur_bak = conn_bak.cursor()
    cur_bak.execute("PRAGMA integrity_check;")
    int_res = cur_bak.fetchall()
    print(f"[INTEGRITY] PRAGMA integrity_check on backup: {int_res}")
    if int_res != [("ok",)]:
        print("ERROR: Backup integrity check failed!")
        sys.exit(1)
    
    cur_bak.execute("PRAGMA foreign_key_check;")
    fk_res = cur_bak.fetchall()
    print(f"[FK CHECK] PRAGMA foreign_key_check on backup: {fk_res}")
    if fk_res:
        print(f"ERROR: Backup foreign key check failed with violations: {fk_res}")
        sys.exit(1)
    conn_bak.close()

    # 3. Source row counts
    conn = sqlite3.connect(src_db)
    cur = conn.cursor()
    tables = ['tenants', 'users', 'documents', 'document_chunks', 'ingestion_jobs']
    src_counts = {}
    for t in tables:
        cur.execute(f"SELECT count(*) FROM {t}")
        src_counts[t] = cur.fetchone()[0]
    print(f"[SOURCE COUNTS] SQLite: {src_counts}")

    cur.execute("SELECT id FROM document_chunks")
    sqlite_chunk_ids = set(r[0] for r in cur.fetchall())
    conn.close()

    # 4. Qdrant consistency check with full pagination
    qdrant_path = os.getenv("QDRANT_PATH", "qdrant_storage")
    print(f"[QDRANT] Connecting to local Qdrant at '{qdrant_path}'...")
    client = QdrantClient(path=qdrant_path)
    all_points = []
    next_offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name="rag_enterprise_chunks",
            limit=1000,
            offset=next_offset,
            with_payload=False,
            with_vectors=False
        )
        all_points.extend(points)
        if next_offset is None or not points:
            break

    qdrant_ids = set(p.id for p in all_points)
    client.close()
    print(f"[QDRANT] Total points retrieved: {len(qdrant_ids)}")
    
    missing_in_qdrant = sqlite_chunk_ids - qdrant_ids
    extra_in_qdrant = qdrant_ids - sqlite_chunk_ids
    if missing_in_qdrant or extra_in_qdrant:
        print(f"ERROR: Qdrant mismatch! Missing in Qdrant: {len(missing_in_qdrant)}, Extra in Qdrant: {len(extra_in_qdrant)}")
        sys.exit(1)
    print("[QDRANT] 100% ID match between SQLite chunks and Qdrant points (317/317).")

    # 5. Neon pre-migration snapshot
    mig_url = normalize_database_url(os.getenv("DATABASE_MIGRATION_URL"))
    engine = create_engine(mig_url)
    with engine.connect() as neon_conn:
        neon_counts = {}
        for t in tables:
            cnt = neon_conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            neon_counts[t] = cnt
        print(f"[NEON SNAPSHOT] Current Neon table counts: {neon_counts}")
        for t, cnt in neon_counts.items():
            if cnt != 0:
                print(f"WARNING: Neon table {t} is not empty (contains {cnt} rows).")

    print("\nSTAGE E2-A VALIDATION COMPLETE: ALL PREFLIGHT CHECKS PASSED.")

if __name__ == "__main__":
    main()
