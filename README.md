# ⚡ Enterprise  RAG System

A production-grade **Retrieval-Augmented Generation (RAG)** application powered by **Groq LLMs**, **SentenceTransformers**, **FAISS + BM25 Hybrid Search**, **FlashRank Cross-Encoder Re-ranking**, and a **Streamlit Web Dashboard** alongside a **FastAPI REST API**.

---

## 🌟 Key Features

* 🔍 **Hybrid Search (BM25 + FAISS)**: Combines keyword search (sparse BM25) with semantic embeddings (dense FAISS) via Reciprocal Rank Fusion (RRF).
* ⚡ **FlashRank Re-Ranking**: Uses CPU cross-encoders (`ms-marco-TinyBERT-L-2-v2`) to re-rank top candidates for optimal relevance.
* 🚀 **Groq LLM Acceleration**: Powered by `llama-3.3-70b-versatile` and `gemma2-9b-it` for sub-second responses.
* 📑 **Source Citations & Page Tracking**: Every response cites exact PDF filenames, 1-indexed page numbers, and snippet previews.
* 🌐 **Interactive Streamlit UI**: User-friendly chat interface with drag-and-drop file uploading and sidebar controls.
* 📡 **FastAPI REST Backend**: Exposes `/api/query`, `/api/upload`, and `/api/health` endpoints with interactive Swagger documentation.

---

## 🛠️ How I Built It: Step-by-Step Architecture

### 1. Ingestion & Metadata Preservation (`dataloader.py`)
Loaded multi-format documents (PDFs, TXT) using LangChain's community loaders. Instead of discarding file source paths or page numbers, I normalized all metadata dynamically to keep track of:
* Document filename.
* PDF 1-indexed page numbers.
* Row indexes for CSVs.

### 2. Chunking & Embeddings (`embedding.py`)
Split large texts into logical chunks using `RecursiveCharacterTextSplitter` with a chunk size of `1000` tokens and `200` overlap. Vectorized the chunks using `all-MiniLM-L6-v2` SentenceTransformer embeddings, generating `384`-dimension vectors.

### 3. FAISS Vector Database (`vectorstore.py`)
Implemented `FaissVectorStore` using `faiss.IndexFlatL2` for high-speed dense vector similarity retrieval on CPU, persisting the vector index and metadata dictionaries locally.

### 4. Sparse BM25 Keyword Search
Added `rank_bm25` (specifically `BM25Okapi`) to tokenize document chunks. This allows the retriever to match exact keywords (e.g. terminology, names, codes) that vector search sometimes misses.

### 5. Reciprocal Rank Fusion (RRF)
Implemented Reciprocal Rank Fusion (RRF) to merge the candidate lists from dense FAISS and sparse BM25:
$$RRF(d) = \sum_{m \in M} \frac{1}{60 + \text{rank}_m(d)}$$
This scores chunks objectively based on their positions in both lists.

### 6. FlashRank Cross-Encoder Re-ranking
Integrated the **FlashRank** re-ranker model (`ms-marco-TinyBERT-L-2-v2`). The model acts as a secondary evaluator, taking the top retrieved context chunks and re-scoring them against the query to return the top 3-5 high-relevance matches.

### 7. Grounded LLM Orchestration (`search.py`)
Integrated Groq's high-speed API (`llama-3.3-70b-versatile`). Structured the system prompt to enforce strict context-grounded rules: the LLM must only use retrieved context, cite page numbers directly, and state if it doesn't know. Included conversational memory tracking for multi-turn Q&A.

### 8. Web Interface & API Hosting (`ui.py`, `api.py`)
* Created a **Streamlit** user interface with interactive toggles for Hybrid search / Reranking.
* Built a **FastAPI** web server with CORS, exposing standard JSON endpoints (`/api/query`, `/api/upload`) for integration into external apps.

---

## 📁 Repository Structure

```text
├── data/                  # Storage folder for PDFs, TXT, CSV, DOCX files
├── src/
│   └── rag/
│       ├── app.py         # Terminal CLI entry point
│       ├── api.py         # FastAPI REST server
│       ├── dataloader.py  # Document ingestion & metadata extraction
│       ├── embedding.py   # Text chunking & SentenceTransformer embeddings
│       ├── search.py      # Conversational RAG engine with Groq LLM
│       ├── ui.py          # Streamlit Web Application
│       └── vectorstore.py # FAISS + BM25 hybrid index & FlashRank reranker
├── .env                   # Environment variables (GROQ_API_KEY)
├── pyproject.toml         # UV package configuration & dependencies
└── README.md              # Project documentation
```

---

## 🛠️ Quickstart Guide

### 1. Prerequisites & Setup
Ensure you have Python 3.10+ and `uv` installed.

```bash
# Clone the repository
git clone https://github.com/Arjit005/RAG.git
cd RAG

# Install dependencies using uv
uv sync
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory and add your Groq API key:

```env
GROQ_API_KEY=your_groq_api_key_here
```

---

## 🚀 Running the Application

### Option A: Streamlit Interactive Web App (Recommended)
```bash
uv run streamlit run src/rag/ui.py
```
Open `http://localhost:8501` in your browser.

### Option B: FastAPI REST Server
```bash
uv run uvicorn rag.api:app --reload --port 8000
```
Interactive API documentation is available at `http://localhost:8000/docs`.

### Option C: Terminal CLI
```bash
uv run python src/rag/app.py
```

---

## 🤝 License
Distributed under the MIT License.
