# 🚢 RAG Intelligence — Render Production Deployment Architecture & Configuration Guide

**Date of Release Audit:** 12 November 2026  
**Repository:** `https://github.com/Arjit005/RAG.git`  
**Target Branch:** `main` (Synchronized & Pushed)  
**Deployment Infrastructure:** Render Cloud Platform (Ohio / `us-east-2`)  
**Deployment Status:** Pre-Deployment Verification Complete & Blueprint Generated (`render.yaml`)

---

## 1. GitHub Synchronization Verification

The local working tree and remote GitHub repository (`Arjit005/RAG`) have been verified and synchronized:
- **Branch:** `main`
- **Latest Commit:** `3b5a7f34ae3ee1455abfdb0bb812d3e4672fcd6a` (`feat: complete Next.js 16 enterprise RAG application and Render deployment configuration`).
- **Synchronized Artifacts (121 files, +22,484 lines):**
  - Production FastAPI backend (`src/rag/api.py`, `src/rag/db/`, `src/rag/llm/`).
  - Production Next.js 16 application (`frontend/`).
  - Render Blueprint specification (`render.yaml`).
  - Production dependency manifest (`requirements.txt` generated via uv).
  - All 11 automated pytest suites (`tests/`).
  - Comprehensive technical documentation (`docs/`).
- **Security & Secret Leakage Pre-Commit Audit:**
  - Verified `.gitignore` actively ignores `.env`, `.env.*`, `*.db`, `*.bak`, `qdrant_storage/`, `faiss_store_backup/`, `*.log`, `node_modules/`, and `.next/`.
  - Staged file inspection confirmed zero private API keys, database credentials, JWT secrets, or production documents were committed.

---

## 2. Backend Service Configuration (Render Web Service)

| Parameter | Specification | Verification & Reason |
|---|---|---|
| **Service Type** | Web Service | Exposes HTTP REST and SSE streaming endpoints |
| **Name** | `rag-intelligence-backend` | Identified in Render Blueprint |
| **Runtime** | Python 3 | Python 3.13 / 3.12 compatible |
| **Region** | **Ohio (`us-east-2`)** | **Mandatory:** Neon PostgreSQL cluster (`ep-lucky-scene-bd4u2eh5-pooler.c-8.us-east-2.aws.neon.tech`) is in Ohio. Locating backend in Ohio ensures sub-5ms database latency. |
| **Root Directory** | `.` (Repository root) | Python package imports use `src.rag.*` |
| **Build Command** | `pip install --upgrade pip && pip install -r requirements.txt` | Installs runtime dependencies: PyTorch, SentenceTransformers, FlashRank, FastAPI, Uvicorn, QdrantClient, Psycopg2 |
| **Start Command** | `uvicorn src.rag.api:app --host 0.0.0.0 --port $PORT` | **Entry point is `src.rag.api:app`** (NOT `main:app`). Listens on Render's dynamic `$PORT` |
| **Health Check Path** | `/api/health` | Returns HTTP 200 with vector store and LLM readiness telemetry |
| **Instance Plan** | **Standard (2 GB RAM, 1 CPU)** | **CRITICAL:** PyTorch (PyTorch CPU runtime ~700MB), `sentence-transformers` (`all-MiniLM-L6-v2` ~400MB), and FlashRank cross-encoder (`TinyBERT` ~250MB) require at least 1.5 GB memory under active search queries. The 512 MB Free tier will encounter OOM kills during model loading. |

---

## 3. Frontend Service Configuration (Render Web Service)

| Parameter | Specification | Verification & Reason |
|---|---|---|
| **Service Type** | Web Service | SSR Next.js 16 Server |
| **Name** | `rag-intelligence-frontend` | Identified in Render Blueprint |
| **Runtime** | Node | Node 20.x LTS |
| **Region** | **Ohio (`us-east-2`)** | Matches backend region for rapid internal routing |
| **Root Directory** | `frontend` | Self-contained Next.js project directory |
| **Build Command** | `npm ci && npm run build` | Verified clean compilation and static page generation |
| **Start Command** | `npm run start -- -p $PORT` | Starts production Next.js server bound to Render's dynamic `$PORT` |
| **Health Check Path** | `/` (or `/_not-found`) | Validates server responding |
| **Instance Plan** | **Starter (512 MB RAM, 0.5 CPU)** | 512 MB is sufficient for Next.js SSR / Node server |

---

## 4. Storage Architecture & Cloud Migration Strategy

### A. Vector Database (Qdrant)
- **Local Storage Caveat on Render:** Render Web Services utilize an ephemeral filesystem. Any files written to `./qdrant_storage` will be wiped during a restart, redeploy, or container migration.
- **Recommended Production Architecture: Qdrant Cloud**
  1. Create a free managed cluster on **Qdrant Cloud** (AWS `us-east-1` or `us-east-2`).
  2. Set `QDRANT_URL=https://<cluster-id>.us-east-1.aws.cloud.qdrant.io:6333` and `QDRANT_API_KEY=<api-key>` in Render environment variables.
  3. Run the one-time vector migration script `scripts/migrate_faiss_to_qdrant.py` against the Qdrant Cloud URL to upload the existing 319 vectors.
- **Alternative (Single-Instance Persistent Disk):** If keeping Qdrant self-hosted on Render, attach a Render Persistent Disk (`/var/data/qdrant`) and set `QDRANT_LOCATION=/var/data/qdrant`. Note that persistent disks prevent zero-downtime rolling deploys.

### B. Relational Storage (PostgreSQL)
- **Engine:** Neon PostgreSQL Serverless in Ohio (`us-east-2`).
- **Connection Mode:** Pooled endpoint with PgBouncer (`-pooler.c-8.us-east-2.aws.neon.tech`) configured in `DATABASE_URL` with `?sslmode=require`.

### C. Uploaded Document Storage
- User uploads are processed in memory and chunked directly into PostgreSQL and Qdrant.
- For raw document archival in multi-instance production, integrate AWS S3 or Cloudflare R2 object storage.

---

## 5. Complete Environment Variable Deployment Checklist

### A. Backend Web Service (`rag-intelligence-backend`)

| Variable Name | Required | Example / Description | Secret? |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | `postgresql://user:pass@ep-lucky-scene-bd4u2eh5-pooler.c-8.us-east-2.aws.neon.tech/neondb?sslmode=require` | 🔒 Yes |
| `JWT_SECRET` | **Yes** | Random 32+ character cryptographic secret (Render generates automatically) | 🔒 Yes |
| `JWT_ALGORITHM` | **Yes** | `HS256` | No |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | **Yes** | `1440` (24 hours) | No |
| `VECTOR_STORE_TYPE` | **Yes** | `qdrant` | No |
| `QDRANT_URL` | **Yes** (Cloud) | `https://your-cluster-id.us-east-1.aws.cloud.qdrant.io:6333` | No |
| `QDRANT_API_KEY` | **Yes** (Cloud) | Qdrant Cloud API token | 🔒 Yes |
| `QDRANT_COLLECTION` | **Yes** | `rag_enterprise_chunks` | No |
| `GROQ_API_KEY` | **Yes** | Primary Groq API key (powers `qwen/qwen3.8-27b`) | 🔒 Yes |
| `GROQ_API_KEY_2` | Optional | Secondary Groq key for multi-key rotation | 🔒 Yes |
| `GEMINI_API_KEY` | **Yes** | Google AI Studio API key (powers `gemini-3.8-flash`) | 🔒 Yes |
| `OPENROUTER_API_KEY` | **Yes** | OpenRouter API key (powers `liquid/lfm-3-1.7b:free`) | 🔒 Yes |
| `EMBEDDING_MODEL` | **Yes** | `all-MiniLM-L6-v2` | No |
| `DEFAULT_LLM_MODEL` | **Yes** | `qwen/qwen3.8-27b` | No |
| `FRONTEND_URL` | **Yes** | `https://rag-intelligence-frontend.onrender.com` (for CORS) | No |
| `PYTHON_VERSION` | **Yes** | `3.13.0` | No |

### B. Frontend Web Service (`rag-intelligence-frontend`)

| Variable Name | Required | Example / Description | Secret? |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | **Yes** | `https://rag-intelligence-backend.onrender.com` (Backend URL) | No |
| `NODE_VERSION` | **Yes** | `20.18.0` | No |

---

## 6. Step-by-Step Render Deployment Sequence

### Option 1: One-Click Render Blueprint (Recommended)
1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **Blueprints** → **New Blueprint Instance**.
3. Connect repository `Arjit005/RAG`.
4. Render automatically parses `render.yaml` and sets up both the `rag-intelligence-backend` and `rag-intelligence-frontend` web services.
5. In the blueprint variables prompt, paste the secret values (`DATABASE_URL`, `QDRANT_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`).
6. Click **Apply**.

### Option 2: Manual Web Service Setup
1. **Deploy Backend First:**
   - Create Web Service → Connect `Arjit005/RAG` (branch `main`).
   - Root Directory: `.`
   - Build Command: `pip install --upgrade pip && pip install -r requirements.txt`
   - Start Command: `uvicorn src.rag.api:app --host 0.0.0.0 --port $PORT`
   - Region: `Ohio (US East)`
   - Plan: `Standard (2 GB)`
   - Add environment variables from Checklist 5A.
   - Deploy and copy backend URL (e.g. `https://rag-backend.onrender.com`).
2. **Deploy Frontend Second:**
   - Create Web Service → Connect `Arjit005/RAG` (branch `main`).
   - Root Directory: `frontend`
   - Build Command: `npm ci && npm run build`
   - Start Command: `npm run start -- -p $PORT`
   - Region: `Ohio (US East)`
   - Plan: `Starter (512 MB)`
   - Add `NEXT_PUBLIC_API_URL=https://rag-backend.onrender.com`.
   - Deploy.
3. **Update CORS:**
   - Go back to Backend service settings → Set `FRONTEND_URL` to the live frontend URL.

---

## 7. Verification, Health Probes & Rollback Plan

### Post-Deployment Health Check
1. **Backend Health Check:**
   ```bash
   curl -s https://rag-backend.onrender.com/api/health
   ```
   *Expected Response:*
   ```json
   {
     "status": "healthy",
     "indexed_documents_count": 6,
     "vector_store_ready": true,
     "groq_llm_ready": true,
     "embedding_model": "all-MiniLM-L6-v2"
   }
   ```
2. **SSE Streaming Check:**
   Initiate an inquiry in the Research Chat interface; verify that token deltas stream in real time and attribution pills display active routing (`qwen/qwen3.8-27b`, `gemini-3.8-flash`, or `liquid/lfm-3-1.7b:free`).

### Rollback Strategy
- **Application Code:** If an issue arises, navigate to Render Dashboard → Service → **Deploys** → Select previous commit `60229ad` → Click **Rollback**.
- **Database Baseline:** Neon database snapshots can be restored instantly via the Neon Console.
