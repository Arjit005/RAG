# RAG Intelligence — Final Portfolio Deployment Guide

## 1. Executive Summary & Architecture

RAG Intelligence is an evidence-grounded multi-modal enterprise AI research platform designed for portfolio evaluation. The system decouples backend retrieval and vector search from the client, communicating through a server-side Backend-for-Frontend (BFF) proxy that guarantees zero browser-side exposure of JWT access tokens and API provider secrets.

```
+-------------------------------------------------------------------------+
|                        Browser Client (Port 3001)                       |
|   - /login: Email/Password form with Quick Demo Credentials Autofill    |
|   - Protected Workspace: Overview, Research Chat, Knowledge Base, etc.  |
|   - Session Transport: HttpOnly Cookie (`rag_session`), SameSite=Lax    |
+------------------------------------+------------------------------------+
                                     |
                                     v
+------------------------------------+------------------------------------+
|                Next.js 16 Server / BFF (Render Free Web)                |
|   - Next.js Proxy Middleware (`/middleware.ts`): Route-level Auth Guard |
|   - BFF Proxy (`/api/proxy/[...path]`): Translates cookie to Bearer     |
|   - Strips client-supplied Authorization headers (anti-spoofing)       |
|   - State-changing CSRF defense via Origin & Referer verification       |
|   - /api/auth/logout: Flushes HttpOnly session cookie                   |
+------------------------------------+------------------------------------+
                                     |
               Private HTTP Network (`BACKEND_INTERNAL_URL`)
                                     |
                                     v
+------------------------------------+------------------------------------+
|               FastAPI Enterprise Backend (Render Free Web)              |
|   - Stateless JWT Verification (HS256, >=32 char secret validation)     |
|   - Strict Multi-Tenancy: DB foreign keys & Qdrant payload filters      |
|   - Hybrid Retrieval Engine: Dense + BM25 + Reciprocal Rank Fusion      |
|   - FlashRank Cross-Encoder Re-ranking (384-dim COSINE embeddings)      |
|   - Multi-Provider Model Router: Groq, Google Gemini, OpenRouter        |
+------------------+----------------------------------+-------------------+
                   |                                  |
                   v                                  v
+------------------+-----------------+  +-------------+-------------------+
|  Neon Serverless PostgreSQL (Ohio) |  |   Qdrant Cloud Managed Cluster  |
|   - Multi-tenant relational schema |  |   - Collection: rag_enterprise  |
|   - Documents, Chunks, Jobs, Users |  |   - 320 Points (Tenant filtered)|
+------------------------------------+  +---------------------------------+
```

---

## 2. Authentication & Session Architecture

### A. Stateless JWT & HttpOnly Session Transport
1. **Login Flow:**
   - User inputs credentials at `/login` or clicks **Auto-fill** to load the pre-configured demo account.
   - Client JS submits `POST /api/proxy/api/auth/token` with `{ email, password }`.
   - The BFF proxy forwards the request upstream to the FastAPI backend.
   - FastAPI verifies credentials via `bcrypt` against PostgreSQL `users`.
   - Upon successful verification, the BFF intercepts the upstream response, extracts `access_token`, attaches an `HttpOnly`, `SameSite=Lax`, `Path=/` cookie named `rag_session` (24h lifespan), and returns a sanitized JSON body with the token redacted.
2. **Authenticated Request Forwarding:**
   - On every request to `/api/proxy/[...path]`, the BFF extracts `rag_session`.
   - It forcibly drops any browser-supplied `Authorization` header to prevent client spoofing.
   - It injects `Authorization: Bearer <cookie_token>` before forwarding to FastAPI.
3. **Session Guards & Middleware:**
   - `frontend/src/middleware.ts` intercepts requests at the edge:
     - Unauthenticated requests to protected pages (`/`, `/chat`, `/documents`, `/pipeline`, `/retrieval`, `/health`, `/audit`, `/settings`) redirect immediately to `/login`.
     - Authenticated requests attempting to load `/login` are redirected to `/`.
4. **Sign Out Flow:**
   - Clicking **Sign Out** in the sidebar calls `apiClient.logout()`.
   - Fires `POST /api/auth/logout`, setting `maxAge: 0` on `rag_session`.
   - Redirects the browser to `/login`.

---

## 3. Demo Account Provisioning

A dedicated demo account is provisioned in the database for evaluator access:

- **Email:** `admin@enterprise.internal`
- **Password:** `EnterpriseAdmin2026!`
- **Role:** `system_admin`
- **Tenant:** `default-tenant`

### Idempotent Provisioning Script
The backend start command in `render.yaml` automatically executes the provisioning script before launching Uvicorn:
```bash
python scripts/provision_demo_user.py && uvicorn src.rag.api:app --host 0.0.0.0 --port $PORT
```
To run manually in development:
```bash
python scripts/provision_demo_user.py
```

---

## 4. Environment Variables Checklist

### Backend Service (`rag-intelligence-backend`)

| Variable | Type | Purpose | Configuration Method |
| :--- | :--- | :--- | :--- |
| `ENV` | Required | Set to `production` to activate strict JWT/CORS validation. | Set in `render.yaml` (`production`) |
| `PYTHON_VERSION` | Required | Python runtime version. | Set in `render.yaml` (`3.13.0`) |
| `DATABASE_URL` | Required | PostgreSQL connection string (Neon pooled endpoint). | **Set in Render Dashboard** |
| `JWT_SECRET_KEY` | Required | Secret for signing HS256 tokens (>= 32 chars). | Generated automatically via `generateValue: true` |
| `JWT_ALGORITHM` | Required | JWT cryptographic signing algorithm. | Set in `render.yaml` (`HS256`) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Required | Token expiration duration in minutes. | Set in `render.yaml` (`1440`) |
| `VECTOR_STORE_TYPE` | Required | Primary vector engine. | Set in `render.yaml` (`qdrant`) |
| `QDRANT_URL` | Required | Qdrant Cloud cluster endpoint. | **Set in Render Dashboard** |
| `QDRANT_API_KEY` | Required | Qdrant Cloud cluster API key. | **Set in Render Dashboard** |
| `QDRANT_COLLECTION` | Required | Active collection name. | Set in `render.yaml` (`rag_enterprise_chunks`) |
| `GROQ_API_KEY` | Optional | Groq API key for primary fast inference. | **Set in Render Dashboard** |
| `GEMINI_API_KEY` | Optional | Google Gemini API key for multimodal reasoning. | **Set in Render Dashboard** |
| `OPENROUTER_API_KEY` | Optional | OpenRouter API key for free-model fallback. | **Set in Render Dashboard** |
| `EMBEDDING_MODEL` | Required | Sentence-Transformers embedding model. | Set in `render.yaml` (`all-MiniLM-L6-v2`) |
| `DEFAULT_LLM_MODEL` | Required | Initial default LLM selection. | Set in `render.yaml` (`qwen/qwen3.8-27b`) |
| `FRONTEND_URL` | Required | Public URL of frontend service to permit in CORS. | **Set in Render Dashboard** (e.g. `https://rag-intelligence-frontend.onrender.com`) |
| `DEMO_USER_EMAIL` | Optional | Email for demo account. | Set in `render.yaml` (`admin@enterprise.internal`) |
| `DEMO_USER_PASSWORD` | Optional | Password for demo account. | Set in Render Dashboard or uses `EnterpriseAdmin2026!` |

### Frontend Service (`rag-intelligence-frontend`)

| Variable | Type | Purpose | Configuration Method |
| :--- | :--- | :--- | :--- |
| `NODE_VERSION` | Required | Node.js version. | Set in `render.yaml` (`20.18.0`) |
| `NODE_ENV` | Required | Environment mode. | Set in `render.yaml` (`production`) |
| `BACKEND_INTERNAL_URL` | Required | Internal private network address to the backend. | Linked via Render Blueprint (`fromService.property: host`) |
| `NEXT_PUBLIC_API_URL` | Optional | Fallback public URL to backend. | **Set in Render Dashboard** (e.g. `https://rag-intelligence-backend.onrender.com`) |
| `FRONTEND_URL` | Optional | Public URL of the frontend for CSRF Origin matching. | **Set in Render Dashboard** |

---

## 5. Deployment Instructions (Render Blueprint)

### Step 1: Connect GitHub Repository
1. Navigate to the **Render Dashboard** (`https://dashboard.render.com`).
2. Click **New +** and select **Blueprint**.
3. Connect your GitHub repository: `Arjit005/RAG`.
4. Render will parse `render.yaml` and discover both services (`rag-intelligence-backend` and `rag-intelligence-frontend`).

### Step 2: Configure Secret Environment Variables
In the Render Blueprint configuration screen, input the required values:
- `DATABASE_URL`: Your Neon PostgreSQL pooled connection string.
- `QDRANT_URL`: Your Qdrant Cloud cluster endpoint.
- `QDRANT_API_KEY`: Your Qdrant Cloud API key.
- `GROQ_API_KEY`: Your Groq API key.
- `GEMINI_API_KEY`: Your Google Gemini API key.
- `OPENROUTER_API_KEY`: Your OpenRouter API key.

### Step 3: Configure Frontend/Backend Public URLs
1. Once deployed, note the assigned public URL for `rag-intelligence-frontend` (e.g., `https://rag-intelligence-frontend.onrender.com`).
2. Update the backend environment variable `FRONTEND_URL` to match this URL so that CORS and CSRF allow requests.
3. Trigger a redeploy of the backend if needed.

---

## 6. Verification & Automated Test Results

The release candidate has been verified using both end-to-end browser automation and backend regression test suites:

### Playwright E2E Suite (Next.js Frontend)
- **Module 1 (Overview Dashboard):** Live metrics from PostgreSQL Neon and Qdrant Cloud rendered (**PASSED**).
- **Module 2 (Research Chat):** Question submission, hybrid retrieval, and citation verification (**PASSED**).
- **Module 3 (Knowledge Base):** Document listing, chunk inspection, and hero dropzone (**PASSED**).
- **Module 4 (Retrieval Explorer):** Dense, sparse BM25, and FlashRank reranking stages (**PASSED**).
- **Module 5 (Pipeline Monitor):** Background ingestion job tracking and state inspection (**PASSED**).
- **Module 6 (System Health):** Component status checks for DB, vector store, and AI router (**PASSED**).
- **Module 7 (Activity & Audit):** Operational audit logs and event history (**PASSED**).
- **Module 8 (Settings):** Retrieval parameters and LLM model priority adjustments (**PASSED**).
- **Module 9 (Document Ingestion E2E):** Drag-and-drop file upload, size checks, and ingestion tracking (**PASSED**).

### Pytest Backend Suite (45/45 Passed)
- `tests/test_render_deployment.py`: 11/11 tests passed (strict production JWT validation, CORS origin lockdown, Qdrant Cloud fail-closed enforcement, tenant isolation).
- `tests/test_model_router.py`: 24/24 tests passed (failover, circuit breaker, rate limit recovery, priority ordering).
- `tests/test_auth_security.py`: 10/10 tests passed (SQL injection defenses, token verification, tenant boundary isolation).

---

## 7. Known Free-Tier Limitations & Mitigations

1. **Ephemeral Local Filesystem:**
   - Render Free Web Services use ephemeral filesystems. Any documents uploaded to local disk during a demo session are processed and indexed into PostgreSQL Neon and Qdrant Cloud immediately. If the container restarts, the processed vector points and relational chunk records persist in Neon and Qdrant, but raw uploaded source files in `/tmp` are wiped. This is normal for containerized architectures.
2. **Cold Starts:**
   - On the Free tier, services spin down after 15 minutes of inactivity. The first request after an idle period may take 30–50 seconds to warm up the container and load the sentence transformer model into memory.
3. **RAM Constraints:**
   - The SentenceTransformer embedding model (`all-MiniLM-L6-v2`) and FlashRank ranker run in CPU memory. On 512 MB Free instances, PyTorch peak memory usage is optimized; avoid concurrent multi-gigabyte document batch ingestions on the free tier.
