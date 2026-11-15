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
    Unified Embedding Pipeline with lazy model loading and batch execution.
    Supports local SentenceTransformer and resilient memory optimization.
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
        logger.info(f"Initialized embedding pipeline configuration: {model_name}")

    @property
    def model(self):
        if self._model is None:
            # Memory guard for constrained environments (e.g. Render 512MB RAM)
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("MALLOC_ARENA_MAX", "2")
            
            logger.info(f"Loading SentenceTransformer model: {self.model_name}")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: List[str], show_progress_bar: bool = False) -> np.ndarray:
        """
        Public encode interface for batches of strings.
        Processes in small micro-batches with garbage collection to protect RAM.
        """
        if not texts:
            return np.array([], dtype=np.float32)

        import gc
        batch_size = 4
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            emb = self.model.encode(batch, show_progress_bar=show_progress_bar)
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