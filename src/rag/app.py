import sys
from pathlib import Path

# Add project root and src directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from rag.dataloader import load_all_documents
    from rag.vectorstore import FaissVectorStore
except ImportError:
    from dataloader import load_all_documents
    from vectorstore import FaissVectorStore


## Example usage

try:
    from rag.search import RAGSearch
except ImportError:
    from search import RAGSearch

import os

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("\n================ ⚡ RAG Intelligence System ⚡ ================")
    print("To launch the interactive Web Interface, run:")
    print("   uv run streamlit run src/rag/ui.py\n")

    search_engine = RAGSearch()
    query = "What is attention mechanism?"
    print(f"[QUERY]: '{query}'\n")
    
    res = search_engine.search_and_answer(query, top_k=3)
    print("--- [AI Answer] ---")
    print(res["answer"])
    
    print("\n--- [Citations & Page Numbers] ---")
    for cit in res.get("citations", []):
        print(f"• Document: {cit['source']} | Page {cit['page']} (Score: {cit['distance']})")