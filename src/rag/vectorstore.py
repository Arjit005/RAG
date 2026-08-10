import os
import faiss
import numpy as np
import pickle
from typing import List, Any
from sentence_transformers import SentenceTransformer
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from rag.embedding import EmbeddingPipeline
except ImportError:
    from embedding import EmbeddingPipeline

from rank_bm25 import BM25Okapi
try:
    from flashrank import Ranker, RerankRequest
except ImportError:
    Ranker = None

class FaissVectorStore:
    def __init__(self, persist_dir: str = "faiss_store", embedding_model: str = "all-MiniLM-L6-v2", chunk_size: int = 1000, chunk_overlap: int = 200):
        self.persist_dir = persist_dir
        os.makedirs(self.persist_dir, exist_ok=True)
        self.index = None
        self.metadata = []
        self.bm25 = None
        self.tokenized_corpus = []
        self.embedding_model = embedding_model
        self.model = SentenceTransformer(embedding_model)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.ranker = None
        print(f"[INFO] Loaded embedding model: {embedding_model}")

    def init_reranker(self):
        if self.ranker is None and Ranker is not None:
            try:
                self.ranker = Ranker()
                print("[INFO] FlashRank cross-encoder reranker initialized.")
            except Exception as e:
                print(f"[WARNING] Could not initialize FlashRank reranker: {e}")
                self.ranker = None

    def _tokenize(self, text: str) -> List[str]:
        return text.lower().split()

    def build_from_documents(self, documents: List[Any]):
        print(f"[INFO] Building vector store from {len(documents)} raw documents...")
        emb_pipe = EmbeddingPipeline(model_name=self.embedding_model, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        chunks = emb_pipe.chunk_documents(documents)
        embeddings = emb_pipe.embed_chunks(chunks)
        metadatas = [{**getattr(chunk, "metadata", {}), "text": chunk.page_content} for chunk in chunks]
        
        self.tokenized_corpus = [self._tokenize(m["text"]) for m in metadatas]
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        
        self.add_embeddings(np.array(embeddings).astype('float32'), metadatas)
        self.save()
        print(f"[INFO] Vector store built with BM25 & FAISS and saved to {self.persist_dir}")

    def add_embeddings(self, embeddings: np.ndarray, metadatas: List[Any] = None):
        dim = embeddings.shape[1]
        if self.index is None:
            self.index = faiss.IndexFlatL2(dim)
        self.index.add(embeddings)
        if metadatas:
            self.metadata.extend(metadatas)
        print(f"[INFO] Added {embeddings.shape[0]} vectors to Faiss index.")

    def save(self):
        faiss_path = os.path.join(self.persist_dir, "faiss.index")
        meta_path = os.path.join(self.persist_dir, "metadata.pkl")
        bm25_path = os.path.join(self.persist_dir, "bm25.pkl")
        
        faiss.write_index(self.index, faiss_path)
        with open(meta_path, "wb") as f:
            pickle.dump(self.metadata, f)
        with open(bm25_path, "wb") as f:
            pickle.dump({"bm25": self.bm25, "corpus": self.tokenized_corpus}, f)
            
        print(f"[INFO] Saved Faiss index, BM25, and metadata to {self.persist_dir}")

    def load(self):
        faiss_path = os.path.join(self.persist_dir, "faiss.index")
        meta_path = os.path.join(self.persist_dir, "metadata.pkl")
        bm25_path = os.path.join(self.persist_dir, "bm25.pkl")
        
        self.index = faiss.read_index(faiss_path)
        with open(meta_path, "rb") as f:
            self.metadata = pickle.load(f)
            
        if os.path.exists(bm25_path):
            with open(bm25_path, "rb") as f:
                data = pickle.load(f)
                self.bm25 = data.get("bm25")
                self.tokenized_corpus = data.get("corpus", [])
        else:
            self.tokenized_corpus = [self._tokenize(m.get("text", "")) for m in self.metadata]
            self.bm25 = BM25Okapi(self.tokenized_corpus)
            
        print(f"[INFO] Loaded Faiss index, BM25, and metadata from {self.persist_dir}")

    def search(self, query_embedding: np.ndarray, top_k: int = 5):
        D, I = self.index.search(query_embedding, top_k)
        results = []
        for idx, dist in zip(I[0], D[0]):
            meta = self.metadata[idx] if idx < len(self.metadata) else None
            results.append({"index": idx, "distance": dist, "metadata": meta})
        return results

    def hybrid_search(self, query_text: str, top_k: int = 5, rr_k: int = 60) -> List[dict]:
        """
        Reciprocal Rank Fusion (RRF) combining FAISS dense vector search & BM25 keyword search.
        """
        fetch_k = max(top_k * 3, 20)
        
        # 1. FAISS Search
        query_emb = self.model.encode([query_text]).astype('float32')
        dense_results = self.search(query_emb, top_k=fetch_k)
        
        # 2. BM25 Search
        tokenized_query = self._tokenize(query_text)
        bm25_scores = self.bm25.get_scores(tokenized_query) if self.bm25 else np.zeros(len(self.metadata))
        sparse_indices = np.argsort(bm25_scores)[::-1][:fetch_k]
        
        # 3. Reciprocal Rank Fusion
        rrf_scores = {}
        
        for rank, res in enumerate(dense_results):
            idx = res["index"]
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (1.0 / (rr_k + rank + 1))
            
        for rank, idx in enumerate(sparse_indices):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (1.0 / (rr_k + rank + 1))
            
        sorted_indices = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]
        
        results = []
        for idx in sorted_indices:
            results.append({
                "index": idx,
                "distance": float(rrf_scores[idx]),
                "metadata": self.metadata[idx] if idx < len(self.metadata) else None
            })
            
        return results

    def rerank(self, query_text: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
        """
        FlashRank Cross-Encoder Re-ranking
        """
        self.init_reranker()
        if not self.ranker or not candidates:
            return candidates[:top_k]
            
        passages = [
            {
                "id": str(c["index"]),
                "text": c["metadata"].get("text", "") if c.get("metadata") else ""
            }
            for c in candidates
        ]
        
        try:
            rerank_req = RerankRequest(query=query_text, passages=passages)
            reranked_passages = self.ranker.rerank(rerank_req)
            
            rerank_dict = {int(p["id"]): p["score"] for p in reranked_passages}
            
            reranked_candidates = []
            for c in candidates:
                idx = c["index"]
                if idx in rerank_dict:
                    c_copy = dict(c)
                    c_copy["distance"] = float(rerank_dict[idx])
                    reranked_candidates.append(c_copy)
                    
            reranked_candidates.sort(key=lambda x: x["distance"], reverse=True)
            return reranked_candidates[:top_k]
        except Exception as e:
            print(f"[WARNING] Reranking failed, returning original candidates: {e}")
            return candidates[:top_k]

    def query(self, query_text: str, top_k: int = 5, use_hybrid: bool = True, use_rerank: bool = True):
        print(f"[INFO] Querying (Hybrid={use_hybrid}, Rerank={use_rerank}) for: '{query_text}'")
        
        candidate_count = top_k * 3 if use_rerank else top_k
        
        if use_hybrid:
            candidates = self.hybrid_search(query_text, top_k=candidate_count)
        else:
            query_emb = self.model.encode([query_text]).astype('float32')
            candidates = self.search(query_emb, top_k=candidate_count)
            
        if use_rerank:
            return self.rerank(query_text, candidates, top_k=top_k)
        
        return candidates[:top_k]

# Example usage
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        from rag.dataloader import load_all_documents
    except ImportError:
        from dataloader import load_all_documents
    docs = load_all_documents("data")
    store = FaissVectorStore("faiss_store")
    store.build_from_documents(docs)
    store.load()
    print(store.query("What is attention mechanism?", top_k=3, use_hybrid=True, use_rerank=True))