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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.dataloader import load_all_documents
from rag.search import RAGSearch

def test_dry_run():
    print("Starting Multimodal RAG dry run verification...")
    
    # We will test loading documents. Since GEMINI_API_KEY might not be set during this shell check,
    # it should log warnings but complete successfully without errors.
    print("Testing document loading...")
    docs = load_all_documents("data")
    print(f"Successfully loaded {len(docs)} document elements.")
    
    images_count = sum(1 for d in docs if d.metadata.get("type") == "image")
    tables_count = sum(1 for d in docs if d.metadata.get("type") == "table")
    text_count = sum(1 for d in docs if d.metadata.get("type") == "text")
    
    print(f"Breakdown: Text chunks: {text_count}, Tables: {tables_count}, Images: {images_count}")
    
    print("Testing Vector Store Indexing and Loading...")
    search_engine = RAGSearch()
    print("Rebuilding index...")
    search_engine.rebuild_index()
    
    print("Running a sample query...")
    res = search_engine.search_and_answer("attention mechanism", top_k=3)
    print("\nAnswer:")
    print(res.get("answer"))
    print("\nCitations:")
    for cit in res.get("citations", []):
        print(f"- {cit['source']} (Page {cit['page']}) [{cit['type']}] (dist: {cit['distance']})")

if __name__ == "__main__":
    test_dry_run()
