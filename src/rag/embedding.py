import os
import sys
import logging
from pathlib import Path
from typing import List, Any, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
import numpy as np

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

class EmbeddingPipeline:
    """
    Unified Embedding Pipeline with zero-RAM API offloading.
    Prioritizes Gemini Serverless Embeddings (384-dim matching Qdrant Cloud),
    completely avoiding PyTorch/SentenceTransformers RAM spikes on Render Free Tier.
    Falls back gracefully to local SentenceTransformer if API key is not configured.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", chunk_size: int = 1000, chunk_overlap: int = 200):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and strictly less than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.model_name = model_name
        self._model = None
        self.gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        logger.info(f"Initialized embedding pipeline. Serverless Gemini active: {bool(self.gemini_key)}")

    def _embed_gemini(self, texts: List[str]) -> List[List[float]]:
        """Generates 384-dimensional embeddings via Google Gemini REST API (zero server RAM)."""
        import json
        import urllib.request

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents?key={self.gemini_key}"
        requests_payload = [
            {
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": t[:4000] if t.strip() else "Empty"}]},
                "outputDimensionality": 384
            }
            for t in texts
        ]
        
        req = urllib.request.Request(
            url,
            data=json.dumps({"requests": requests_payload}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read().decode("utf-8"))
            return [e["values"] for e in res["embeddings"]]

    @property
    def model(self):
        class _ModelWrapper:
            def __init__(self, parent):
                self.parent = parent
            def encode(self, texts, show_progress_bar=False):
                return self.parent.encode(texts, show_progress_bar=show_progress_bar)

        if self.gemini_key:
            return _ModelWrapper(self)

        if self._model is None:
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("MALLOC_ARENA_MAX", "2")
            logger.info(f"Loading local SentenceTransformer model: {self.model_name}")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: List[str], show_progress_bar: bool = False) -> np.ndarray:
        """
        Public encode interface for batches of strings.
        Routes to Gemini Serverless Embeddings (384-dim) for 0 MB RAM usage.
        """
        if not texts:
            return np.array([], dtype=np.float32)

        # 1. Serverless API Strategy (Zero RAM, zero CPU bottleneck)
        if self.gemini_key:
            try:
                # Batch in groups of 25 to respect Gemini limits
                batch_size = 25
                all_embs = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    batch_embs = self._embed_gemini(batch)
                    all_embs.extend(batch_embs)
                return np.array(all_embs, dtype=np.float32)
            except Exception as e:
                logger.warning(f"Gemini serverless embedding failed, falling back to local: {e}")

        # 2. Local Fallback with Micro-batching
        import gc
        batch_size = 4
        all_embeddings = []
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            emb = self._model.encode(batch, show_progress_bar=show_progress_bar)
            all_embeddings.extend(emb)
            gc.collect()

        return np.array(all_embeddings, dtype=np.float32)

    def chunk_documents(self, documents: List[Any]) -> List[Any]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = splitter.split_documents(documents)
        logger.info(f"Split {len(documents)} documents into {len(chunks)} chunks.")
        return chunks

    def embed_chunks(self, chunks: List[Any]) -> np.ndarray:
        texts = [chunk.page_content for chunk in chunks]
        logger.info(f"Generating embeddings for {len(texts)} chunks...")
        embeddings = self.encode(texts, show_progress_bar=True)
        logger.info(f"Embeddings shape: {embeddings.shape}")
        return embeddings