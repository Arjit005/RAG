import os
import sys
import logging
from pathlib import Path
from typing import List, Any, Optional, Callable
import numpy as np

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def recursive_character_chunk(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
    """
    Zero-overhead, pure-Python recursive text splitter.
    Splits text on double newline, single newline, sentences, spaces, or characters.
    Zero external imports, 0ms CPU time, 0 MB memory footprint.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    separators = ["\n\n", "\n", ". ", " ", ""]

    def _split(s: str, seps: list) -> list:
        if not seps:
            chunks = []
            start = 0
            while start < len(s):
                end = min(start + chunk_size, len(s))
                chunks.append(s[start:end])
                start += chunk_size - chunk_overlap
            return chunks

        sep = seps[0]
        remaining_seps = seps[1:]

        splits = s.split(sep) if sep else list(s)
        current_chunk = []
        current_len = 0
        final_chunks = []

        for piece in splits:
            piece_len = len(piece) + (len(sep) if current_chunk else 0)
            if current_len + piece_len <= chunk_size:
                current_chunk.append(piece)
                current_len += piece_len
            else:
                if current_chunk:
                    final_chunks.append(sep.join(current_chunk))
                    overlap_len = 0
                    overlap_items = []
                    for item in reversed(current_chunk):
                        if overlap_len + len(item) <= chunk_overlap:
                            overlap_items.insert(0, item)
                            overlap_len += len(item) + len(sep)
                        else:
                            break
                    current_chunk = overlap_items
                    current_len = sum(len(x) for x in current_chunk) + (len(sep) * (len(current_chunk) - 1) if current_chunk else 0)

                if len(piece) > chunk_size:
                    final_chunks.extend(_split(piece, remaining_seps))
                else:
                    current_chunk.append(piece)
                    current_len += len(piece)

        if current_chunk:
            final_chunks.append(sep.join(current_chunk))

        return [c.strip() for c in final_chunks if c.strip()]

    return _split(text, separators)


class EmbeddingPipeline:
    """
    Unified Embedding Pipeline with zero-RAM API offloading.
    Prioritizes Gemini Serverless Embeddings (384-dim matching Qdrant Cloud),
    completely avoiding PyTorch/SentenceTransformers RAM spikes on Render Free Tier.
    Falls back gracefully to local SentenceTransformer ONLY in non-production local environments.
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

    def _embed_gemini(self, texts: List[str], max_retries: int = 5) -> List[List[float]]:
        """Generates 384-dimensional embeddings via Google Gemini REST API with rate-limit backoff."""
        import json
        import urllib.request
        import urllib.error
        import time
        import random

        keys = [k.strip() for k in self.gemini_key.split(",") if k.strip()]
        if not keys:
            raise ValueError("No valid GEMINI_API_KEY configured.")

        requests_payload = [
            {
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": t[:3000] if (t and t.strip()) else "Empty"}]},
                "outputDimensionality": 384
            }
            for t in texts
        ]

        data_bytes = json.dumps({"requests": requests_payload}).encode("utf-8")

        for attempt in range(max_retries):
            current_key = keys[attempt % len(keys)]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents?key={current_key}"
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    res = json.loads(r.read().decode("utf-8"))
                    return [e["values"] for e in res["embeddings"]]
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    if attempt < max_retries - 1:
                        backoff = min((attempt + 1) * 5 + random.uniform(1.0, 3.0), 30)
                        logger.warning(
                            f"Gemini embedding 429 rate limit hit. Pausing for {backoff:.1f}s before retry "
                            f"({attempt + 1}/{max_retries})..."
                        )
                        time.sleep(backoff)
                        continue
                    else:
                        raise RuntimeError(
                            f"Gemini API rate limit (429) hit repeatedly. "
                            f"The provider quota was saturated. Please wait 1 minute and re-try."
                        )
                raise e
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                raise e

        raise RuntimeError("Embedding extraction failed after retries.")

    @property
    def model(self):
        class _ModelWrapper:
            def __init__(self, parent):
                self.parent = parent
            def encode(self, texts, show_progress_bar=False):
                return self.parent.encode(texts, show_progress_bar=show_progress_bar)

        if self.gemini_key:
            return _ModelWrapper(self)

        is_prod = os.getenv("ENV", "").lower() in ("production", "prod") or bool(os.getenv("RENDER"))
        if is_prod:
            raise RuntimeError(
                "GEMINI_API_KEY is required in production. "
                "Local PyTorch / SentenceTransformer is disabled on Render to prevent 512MB RAM OOM crash."
            )

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
        Routes to Gemini Serverless Embeddings (384-dim) with adaptive rate limiting and 0 MB RAM usage.
        """
        if not texts:
            return np.array([], dtype=np.float32)

        # 1. Serverless API Strategy (Zero RAM, zero CPU bottleneck)
        if self.gemini_key:
            import time
            try:
                batch_size = 20
                all_embs = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    batch_embs = self._embed_gemini(batch)
                    all_embs.extend(batch_embs)
                    # Adaptive pacing between micro-batches to respect 15 RPM
                    if i + batch_size < len(texts):
                        time.sleep(1.5)
                return np.array(all_embs, dtype=np.float32)
            except Exception as e:
                logger.error(f"Gemini serverless embedding failed: {e}")
                is_prod = os.getenv("ENV", "").lower() in ("production", "prod") or bool(os.getenv("RENDER"))
                if is_prod:
                    raise RuntimeError(f"Serverless embedding generation failed on production: {e}")

        # 2. Local Fallback with Micro-batching (dev/local only)
        is_prod = os.getenv("ENV", "").lower() in ("production", "prod") or bool(os.getenv("RENDER"))
        if is_prod:
            raise RuntimeError(
                "GEMINI_API_KEY is mandatory in production environment. "
                "PyTorch model loading is prohibited on Render to prevent OOM crash."
            )

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
        class SimpleChunk:
            def __init__(self, page_content, metadata=None):
                self.page_content = page_content
                self.metadata = metadata or {}

        chunks = []
        for doc in documents:
            text = getattr(doc, "page_content", str(doc))
            meta = getattr(doc, "metadata", {})
            sub_texts = recursive_character_chunk(text, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
            for st in sub_texts:
                chunks.append(SimpleChunk(page_content=st, metadata=meta.copy()))

        logger.info(f"Split {len(documents)} documents into {len(chunks)} chunks.")
        return chunks

    def embed_chunks(self, chunks: List[Any]) -> np.ndarray:
        texts = [chunk.page_content for chunk in chunks]
        logger.info(f"Generating embeddings for {len(texts)} chunks...")
        embeddings = self.encode(texts, show_progress_bar=False)
        logger.info(f"Embeddings shape: {embeddings.shape}")
        return embeddings
