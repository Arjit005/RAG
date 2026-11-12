from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseVectorStore(ABC):
    """
    Abstract interface for vector search engines (Qdrant, FAISS fallback).
    Enforces identical retrieval contracts, payload metadata handling, and lifecycle methods.
    """

    @abstractmethod
    def add_documents(
        self,
        tenant_id: str,
        document_id: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]]
    ) -> List[str]:
        """
        Idempotently adds chunks and vectors to the vector store with payload metadata.
        Returns the list of persistent point/chunk IDs.
        """
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        tenant_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Performs dense vector similarity search with optional tenant pre-filtering.
        """
        pass

    @abstractmethod
    def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        top_k: int = 5,
        tenant_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        rr_k: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Performs hybrid dense + sparse retrieval with Reciprocal Rank Fusion.
        """
        pass

    @abstractmethod
    def delete_document(self, document_id: str, tenant_id: Optional[str] = None) -> bool:
        """
        Deletes all chunks/points associated with a document_id.
        """
        pass

    @abstractmethod
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        use_hybrid: bool = True,
        use_rerank: bool = True,
        tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes query retrieval with optional tenant filtering, hybrid fusion, and reranking.
        """
        pass
