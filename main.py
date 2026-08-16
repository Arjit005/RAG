import sys
import uuid
# Mock uuid_utils to bypass Windows AppLocker/WDAC DLL block
class CompatMock:
    @staticmethod
    def uuid7():
        return uuid.uuid4()
class UUIDUtilsMock:
    compat = CompatMock()
sys.modules['uuid_utils'] = UUIDUtilsMock()
sys.modules['uuid_utils.compat'] = CompatMock()

import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from src.rag.search import RAGSearch

load_dotenv()

app = FastAPI(
    title="RAG API",
    description="RAG application using FAISS and Groq",
    version="1.0.0",
)

# Create the RAG engine once when the server starts
search_engine = RAGSearch()


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/ask")
def ask(
    question: str,
    top_k: int = 3
):
    """
    Ask a question to the RAG system.

    Example:
    /ask?question=What%20is%20attention%20mechanism%3F
    """

    if not question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )

    try:
        result = search_engine.search_and_answer(
            query=question,
            top_k=top_k,
            use_hybrid=True,
            use_rerank=True
        )

        return {
            "question": question,
            "answer": result.get("answer"),
            "citations": result.get("citations", [])
        }

    except Exception as e:
        print(f"[ERROR] RAG request failed: {e}")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
