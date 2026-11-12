# Deployment & Operations Guide

## 1. System Requirements
- Node.js >= 18.17.0 (Current: Node.js v25.2.1, npm 11.6.2)
- Python >= 3.10 (Current: Python 3.13.14 with virtual environment)
- PostgreSQL (Neon Cloud instance)
- Vector DB: Qdrant (local persistent storage or Qdrant Cloud cluster)

---

## 2. Environment Variables

### Backend (`.env` in root)
```ini
DATABASE_URL=postgresql://neondb_owner:npg_8K2vSdfbtyoU@ep-calm-river-a4m11qff-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
VECTOR_STORE_TYPE=qdrant
QDRANT_STORAGE_PATH=./qdrant_storage
QDRANT_COLLECTION_NAME=rag_enterprise_chunks
EMBEDDING_MODEL=all-MiniLM-L6-v2
JWT_SECRET_KEY=enterprise_super_secret_jwt_key_2026_rag_platform_change_in_prod
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
GROQ_API_KEY=<your_groq_api_key>
GEMINI_API_KEY=<your_gemini_api_key>
```

### Frontend (`frontend/.env.local`)
```ini
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

---

## 3. Starting the Applications

### Primary: Next.js Enterprise Application
```powershell
# 1. Start FastAPI backend (Port 8000)
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe -m uvicorn src.rag.api:app --host 127.0.0.1 --port 8000

# 2. Start Next.js frontend (Port 3001)
cd frontend
npm run start -- -p 3001
# Application accessible at: http://localhost:3001
```

### Fallback: Streamlit Application (Intact Backup)
```powershell
# The Streamlit application remains completely preserved as a fallback:
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe -m streamlit run src/rag/ui.py --server.port 8501
# Fallback accessible at: http://localhost:8501
```

---

## 4. Rollback Procedure
If any unexpected issue occurs on Next.js:
1. Streamlit frontend code is 100% intact in `src/rag/ui.py` and `src/rag/frontend/`.
2. Both frontends share the identical FastAPI backend and database without schema modifications.
3. Simply direct user traffic to `http://localhost:8501` to immediately revert to Streamlit without downtime or data changes.
