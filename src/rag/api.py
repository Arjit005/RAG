import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Setup sys.path for internal imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from rag.search import RAGSearch
except ImportError:
    from search import RAGSearch

# Initialize FastAPI App
app = FastAPI(
    title="RAG Intelligence Enterprise API",
    description="Production REST API for Document Intelligence, Hybrid Vector Search, and Groq LLM Querying.",
    version="1.0.0"
)

# Enable CORS for external frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared RAG Instance
rag_engine: Optional[RAGSearch] = None

def get_rag_engine() -> RAGSearch:
    global rag_engine
    if rag_engine is None:
        rag_engine = RAGSearch()
    return rag_engine

# Pydantic Models
class QueryRequest(BaseModel):
    query: str = Field(..., description="User question or query string", example="What is attention mechanism?")
    top_k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    model: str = Field("llama-3.3-70b-versatile", description="Groq LLM model name")
    use_hybrid: bool = Field(True, description="Enable BM25 + FAISS Hybrid Search")
    use_rerank: bool = Field(True, description="Enable FlashRank Cross-Encoder Re-ranking")
    chat_history: Optional[List[Dict[str, Any]]] = Field(default=[], description="Previous conversation history")

class Citation(BaseModel):
    source: str
    page: int
    snippet: str
    distance: float

class QueryResponse(BaseModel):
    query: str
    answer: str
    citations: List[Citation]
    model: str
    hybrid_enabled: bool
    rerank_enabled: bool

class HealthResponse(BaseModel):
    status: str
    indexed_documents_count: int
    vector_store_ready: bool
    groq_llm_ready: bool
    embedding_model: str

# Endpoints
@app.get("/", tags=["General"])
def root():
    return {
        "message": "Welcome to RAG Intelligence Enterprise API 🚀",
        "documentation": "/docs",
        "health": "/api/health"
    }

@app.get("/api/health", response_model=HealthResponse, tags=["General"])
def health_check():
    engine = get_rag_engine()
    data_dir = Path("data")
    existing_docs = list(data_dir.glob("**/*.*")) if data_dir.exists() else []
    
    faiss_path = Path("faiss_store/faiss.index")
    
    return {
        "status": "healthy",
        "indexed_documents_count": len(existing_docs),
        "vector_store_ready": faiss_path.exists(),
        "groq_llm_ready": engine.llm is not None,
        "embedding_model": engine.embedding_model
    }

@app.post("/api/query", response_model=QueryResponse, tags=["RAG Search"])
def query_rag(req: QueryRequest):
    engine = get_rag_engine()
    if req.model != engine.llm_model:
        engine.llm_model = req.model
        engine.init_llm()
        
    try:
        res = engine.search_and_answer(
            query=req.query,
            top_k=req.top_k,
            chat_history=req.chat_history,
            use_hybrid=req.use_hybrid,
            use_rerank=req.use_rerank
        )
        
        return {
            "query": req.query,
            "answer": res["answer"],
            "citations": res["citations"],
            "model": req.model,
            "hybrid_enabled": req.use_hybrid,
            "rerank_enabled": req.use_rerank
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing RAG search: {str(e)}")

@app.post("/api/upload", tags=["Document Management"])
async def upload_documents(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
        
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    saved_files = []
    
    for file in files:
        ext = file.filename.split(".")[-1].lower()
        subfolder = data_dir / (f"{ext}_files" if ext in ["txt", "csv", "json"] else ext)
        subfolder.mkdir(parents=True, exist_ok=True)
        
        file_path = subfolder / file.filename
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        saved_files.append(file.filename)
        
    # Rebuild Index
    engine = get_rag_engine()
    engine.rebuild_index()
    
    return {
        "message": f"Successfully uploaded and indexed {len(saved_files)} file(s).",
        "uploaded_files": saved_files
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
