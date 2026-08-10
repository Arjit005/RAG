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
git clone https://github.com/your-username/RAG.git
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
