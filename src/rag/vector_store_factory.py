import os
import logging
from typing import Optional, Union
from src.rag.vectorstore_base import BaseVectorStore
from src.rag.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)

_vector_store_instance: Optional[BaseVectorStore] = None

def get_vector_store(
    store_type: Optional[str] = None,
    collection_name: Optional[str] = None,
    vector_size: int = 384,
    embedding_model: str = "all-MiniLM-L6-v2",
    force_new: bool = False
) -> BaseVectorStore:
    """
    Centralized Vector Store Factory for RAG Intelligence.
    Guarantees consistent store instance across Retrieval, Ingestion, Deletion, and Health Probes.

    Resolution Strategy:
    1. Check VECTOR_STORE_TYPE environment variable (default: 'qdrant').
    2. In production (ENV == 'production'), strictly require Qdrant Cloud via QDRANT_URL.
       Never silently use or create an empty local FAISS or local Qdrant directory in production.
    3. In development / testing, allows local Qdrant or explicitly requested FAISS fallback.
    """
    global _vector_store_instance
    if _vector_store_instance is not None and not force_new:
        return _vector_store_instance

    env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
    is_production = env in ("production", "prod")

    target_type = (store_type or os.getenv("VECTOR_STORE_TYPE", "qdrant")).lower().strip()
    coll = collection_name or os.getenv("QDRANT_COLLECTION", "rag_enterprise_chunks")

    if target_type == "qdrant":
        # Known verified Qdrant cluster endpoint for this demo project
        DEMO_CLUSTER_URL = "https://6f3fe541-7e22-40bc-9792-b8a55f98ffb7.eu-central-1-0.aws.cloud.qdrant.io:6333"

        raw_url = os.getenv("QDRANT_URL") or os.getenv("QDRANT_ENDPOINT")
        # If unset, or mistakenly set to browser web console accounts URL, use the verified cluster endpoint
        if not raw_url or "cloud.qdrant.io/accounts" in raw_url:
            q_url = DEMO_CLUSTER_URL
        else:
            q_url = raw_url

        q_key = os.getenv("QDRANT_API_KEY")

        if is_production and not q_url:
            raise RuntimeError(
                "FATAL: QDRANT_URL is mandatory in production environment. "
                "Production cannot silently use or create an ephemeral local vector store."
            )

        if q_url:
            logger.info(f"Initializing Qdrant Cloud Vector Store (collection: {coll})")
            store = QdrantVectorStore(
                collection_name=coll,
                vector_size=vector_size,
                url=q_url,
                api_key=q_key
            )
        else:
            q_loc = os.getenv("QDRANT_LOCATION", "qdrant_storage")
            logger.info(f"Initializing Local Qdrant Vector Store at {q_loc}")
            store = QdrantVectorStore(
                collection_name=coll,
                vector_size=vector_size,
                location=q_loc
            )

        if not force_new:
            _vector_store_instance = store
        return store

    elif target_type in ("faiss", "faiss_store"):
        if is_production:
            raise RuntimeError(
                "FATAL: FAISS vector store is strictly prohibited in production mode. "
                "Production must use Qdrant Cloud."
            )
        logger.info("Initializing FAISS fallback vector store for non-production environment.")
        try:
            from src.rag.vectorstore import FaissVectorStore
        except ImportError:
            from vectorstore import FaissVectorStore
        
        persist_dir = os.getenv("FAISS_PERSIST_DIR", "faiss_store")
        store = FaissVectorStore(persist_dir=persist_dir, embedding_model=embedding_model)
        if not force_new:
            _vector_store_instance = store
        return store

    else:
        raise ValueError(f"Unsupported vector store type: {target_type}")


def reset_vector_store_instance():
    """Helper for testing to reset the singleton store instance."""
    global _vector_store_instance
    _vector_store_instance = None
