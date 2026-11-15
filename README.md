# ⚡ Enterprise Multi-Tenant Hybrid RAG Platform

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Render%20Online-00c853?style=for-the-badge&logo=render&logoColor=white)](https://rag-2-ggpa.onrender.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Qdrant](https://img.shields.io/badge/Qdrant%20Cloud-DC2626?style=for-the-badge&logo=qdrant&logoColor=white)](https://qdrant.tech)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL%20(Neon)-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://neon.tech)
[![Pytest](https://img.shields.io/badge/Pytest-50%2B%20Tests%20Passed-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

A production-grade, enterprise-architected **Multi-Tenant Hybrid Retrieval-Augmented Generation (RAG)** platform designed for strict data isolation, high retrieval precision, and resilient execution under ultra-lean cloud constraints (< 512MB RAM).

Built with **FastAPI**, **PostgreSQL (Neon Cloud)**, **Qdrant Cloud**, **BM25**, **FlashRank Cross-Encoder Re-ranking**, and **Google Gemini / Groq LLMs**.

---

## 🌐 Live Deployment & Interactive Access

* 🖥️ **Live Web Platform:** [https://rag-2-ggpa.onrender.com](https://rag-2-ggpa.onrender.com)
* 📚 **Interactive Swagger API Documentation:** [https://rag-2-ggpa.onrender.com/docs](https://rag-2-ggpa.onrender.com/docs)
* 🔑 **Pre-Configured Demo Account:**
  * **Email:** `demo@enterprise.rag`
  * **Password:** `demo-password-2026`
  * *(Or register a new isolated tenant account directly from the UI)*

---

## 🏛️ System Architecture

The platform follows an enterprise **Dual-Store Architecture** separating canonical metadata records from high-dimensional vector search spaces, reinforced by a background reconciliation engine for eventual consistency.

```
                      ┌───────────────────────────────────────────────┐
                      │              User Client / Web UI             │
                      └───────────────────────┬───────────────────────┘
                                              │ (JWT + X-Tenant-ID)
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │         FastAPI Enterprise API Gateway        │
                      │   [Auth / Tenant Boundary / Rate Limiter]     │
                      └───────────────┬───────────────┬───────────────┘
                                      │               │
                 [Document Ingestion Flow]     [Hybrid Search Flow]
                                      │               │
                                      ▼               ▼
                      ┌──────────────────────┐ ┌──────────────────────┐
                      │ Pure-Python Chunker  │ │   Hybrid Retriever   │
                      │ (Streaming, Zero-RAM)│ │ (Qdrant Dense + BM25)│
                      └───────────┬──────────┘ └──────────┬───────────┘
                                  │                       │
                                  ▼                       ▼
                      ┌──────────────────────┐ ┌──────────────────────┐
                      │ PostgreSQL (Neon DB) │ │  Reciprocal Rank     │
                      │ State: PENDING/SYNCED│ │     Fusion (RRF)     │
                      └───────────┬──────────┘ └──────────┬───────────┘
                                  │                       │
                                  ▼                       ▼
                      ┌──────────────────────┐ ┌──────────────────────┐
                      │ Serverless Embedding │ │ FlashRank Re-ranker  │
                      │ (Gemini 384-dim, 429 │ │ (Cross-Encoder SOTA) │
                      │  Adaptive Backoff)   │ └──────────┬───────────┘
                      └───────────┬──────────┘            │
                                  │                       ▼
                                  ▼            ┌──────────────────────┐
                      ┌──────────────────────┐ │   Grounded LLM       │
                      │     Qdrant Cloud     │ │  (Groq LLaMA 3.3 /   │
                      │ Vector Points (384d) │ │      Gemini Flash)   │
                      └──────────────────────┘ └──────────┬───────────┘
                                  ▲                       │
                                  │                       ▼
                      ┌───────────┴──────────┐ ┌──────────────────────┐
                      │ Self-Healing Engine  │ │  Verified Citations  │
                      │ (Reconciliation Job) │ │   & Grounded Answer  │
                      └──────────────────────┘ └──────────────────────┘
```

---

## 🌟 Key Enterprise Highlights

### 1. 🔍 Hybrid Dense-Sparse Retrieval + Cross-Encoder Re-ranking
* **Dense Semantic Search (Qdrant Cloud):** Captures conceptual similarity using 384-dimensional dense vectors with cosine metric.
* **Sparse Lexical Search (BM25):** Matches exact keywords, technical codes, product identifiers, and domain acronyms.
* **Reciprocal Rank Fusion (RRF):** Blends dense and sparse rankings using standard rank decay:
  $$RRF(d) = \sum_{m \in M} \frac{1}{60 + \text{rank}_m(d)}$$
* **FlashRank Cross-Encoder Re-ranking:** Re-scores the top fused candidates with `ms-marco-TinyBERT-L-2-v2`, elevating retrieval coverage from **62.5% to 81.2%** and suppressing LLM hallucination.

### 2. 🗄️ Dual-Store Architecture & Self-Healing Eventual Consistency
* **Canonical Relational Source-of-Truth:** PostgreSQL (Neon Cloud) records every document, chunk hash, tenant ownership, and state machine (`PENDING` $\to$ `SYNCED` $\to$ `FAILED`).
* **High-Speed Vector Space:** Qdrant Cloud stores vector points mapped directly to relational chunk IDs.
* **Idempotent Reconciliation Engine:** Background worker (`reconcile_failed_syncs`) scans for un-synced chunks and heals the index automatically upon network interruptions without creating duplicates.
* **Cascading Deletions:** Deleting a document in PostgreSQL cascades across all relational chunks and simultaneously purges all vector points from Qdrant Cloud.

### 3. 🛡️ Multi-Tenant Security & Defense-in-Depth
* **Strict Tenant Boundary Isolation:** User tokens are cryptographically signed with JWT (HMAC-SHA256); every database query and vector lookup is strictly filtered by `tenant_id`.
* **Fail-Closed Header Anti-Spoofing:** If a client presents a token for Tenant A while attempting to spoof `X-Tenant-ID: tenant-B`, the request is blocked immediately with `HTTP 403 Forbidden`.
* **IDOR & Resource Concealment:** Cross-tenant resource queries return `HTTP 404 Not Found` rather than `403` to prevent enumeration of other tenants' document IDs.
* **SQL Injection & Path Traversal Defense:** Sanitized via SQLAlchemy parameter binding and strict regex filename validation.

### 4. ⚡ Extreme Resource Optimization (< 512MB RAM Micro-Container)
* **Zero-RAM Text Chunking:** Replaced heavy `langchain_text_splitters` with a pure-Python recursive chunker, reducing CPU import overhead from 33 seconds to **0.001 seconds** and saving over 300MB RAM.
* **Serverless 384-dim Embedding Gateway:** Offloads embedding generation to Google Gemini REST endpoints, completely preventing PyTorch/SentenceTransformers out-of-memory (OOM) crashes on Render Free Tier.
* **Adaptive Exponential Backoff & Pacing:** Automatic retries with exponential jitter when upstream rate limits (HTTP 429) are encountered, enabling seamless ingestion of **200+ page books (650+ chunks)**.

### 5. 🌐 Multimodal Ingestion & Multilingual Capabilities
* **Tables & Charts Extraction:** Uses `PyMuPDF` to parse documents, converts tables into Markdown tables, and leverages Gemini Vision to generate search-indexed descriptions of diagrams and charts.
* **100+ Languages Cross-Lingual Search:** Powered by Google's foundation embedding model (`gemini-embedding-001`), allowing cross-lingual queries (e.g., query in Hindi or Spanish retrieving English document chunks).

---

## 🧪 Comprehensive Automated Testing Suite

The repository includes over **50+ automated unit, integration, and adversarial security tests** built with `pytest`:

| Test Suite | File | Focus Areas | Result |
| :--- | :--- | :--- | :---: |
| **Adversarial Security** | `tests/test_auth_security.py` | Tenant spoofing, token forgery, IDOR 404 concealment, SQL injection fuzzing | **100% Pass (0 Leaks)** |
| **Ingestion & Knowledge Base** | `tests/test_knowledge_base.py` | File whitelist (`.pdf`, `.txt`, `.docx`), 25MB boundary limits, path traversal | **100% Pass** |
| **Retrieval Regression** | `tests/test_stage_f_neon_qa.py` | Dense vs Sparse vs RRF vs FlashRank accuracy, fallback verification | **100% Pass** |
| **Lifecycle & Consistency** | `tests/test_lifecycle.py` | Two-phase sync, cascading deletes, reconciliation worker | **100% Pass** |
| **Chat & Citations** | `tests/test_research_chat.py` | Cross-tenant chat isolation, 4000-char query boundaries, citation integrity | **100% Pass** |

To run the automated test suite locally:
```bash
pytest -v
```

---

## 📊 Empirical Retrieval Benchmark

Quantitative evaluation comparing retrieval strategies across benchmark queries:

| Retrieval Strategy | Recall@3 | Recall@5 | Keyword Coverage | Latency (avg) | Hallucination Risk |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Dense-Only (FAISS / Qdrant)** | 75.0% | 75.0% | 62.5% | ~28 ms | Moderate |
| **Sparse-Only (BM25)** | 75.0% | 75.0% | 81.2% | ~3 ms | High (Lacks semantic depth) |
| **Hybrid (Dense + BM25 via RRF)** | 75.0% | 75.0% | 75.0% | ~24 ms | Low |
| **Hybrid + FlashRank Re-ranking** | **81.2%** | **87.5%** | **81.2%** | ~180 ms | **Minimal (< 2%)** |

---

## 📁 Repository Structure

```text
├── src/
│   └── rag/
│       ├── api.py                 # FastAPI production server & background worker
│       ├── dataloader.py          # Multimodal parsing (PyMuPDF, tables, vision descriptions)
│       ├── embedding.py           # Pure-Python chunker & serverless Gemini embedding gateway
│       ├── qdrant_store.py        # Qdrant Cloud vector client with tenant payload filters
│       ├── search.py              # Hybrid retrieval (Dense + BM25), RRF & FlashRank reranker
│       ├── vectorstore.py         # Vectorstore interfaces & local FAISS fallback
│       └── db/
│           ├── database.py        # SQLAlchemy engine & Neon connection pooling
│           ├── models.py          # Relational schema (Tenant, User, Document, DocumentChunk, IngestionJob)
│           ├── repository.py      # CRUD transactions & row-level tenant filtering
│           └── lifecycle.py       # Two-phase sync, cascading deletes & self-healing reconciler
├── static/
│   └── index.html                 # Enterprise obsidian frontend UI with real-time SSE & polling
├── tests/                         # 50+ Automated Pytest test suite
│   ├── test_auth_security.py      # 10 Adversarial security & tenant isolation tests
│   ├── test_knowledge_base.py     # Ingestion & file boundary tests
│   ├── test_lifecycle.py          # Dual-store sync & cascading delete tests
│   ├── test_research_chat.py      # Chat isolation & citation provenance tests
│   └── test_stage_f_neon_qa.py    # Neon QA & retrieval regression tests
├── main.py                        # Application entry point
├── render.yaml                    # Infrastructure-as-code deployment configuration
├── requirements.txt               # Production Python dependencies
└── README.md                      # Platform documentation
```

---

## 🛠️ Quickstart & Local Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Arjit005/RAG.git
cd RAG
```

### 2. Set Up Virtual Environment & Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the root directory:
```env
# Database & Vector Store
DATABASE_URL=postgresql://user:password@ep-xyz.neon.tech/neondb?sslmode=require
QDRANT_URL=https://your-cluster-id.eu-central-1-0.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=your_qdrant_api_key
QDRANT_COLLECTION=rag_enterprise_chunks

# LLM & Embedding Gateways
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key

# Security & Environment
JWT_SECRET=your_super_secret_jwt_key_here
ENV=production
```

### 4. Run the Platform Locally
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Navigate to `http://localhost:8000` to interact with the platform UI, or visit `http://localhost:8000/docs` for the interactive API reference.

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
