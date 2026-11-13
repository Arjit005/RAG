import os
import uuid
import logging
from typing import List, Dict, Any, Optional
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from src.rag.vectorstore_base import BaseVectorStore
from rank_bm25 import BM25Okapi
try:
    from flashrank import Ranker, RerankRequest
except ImportError:
    Ranker = None

logger = logging.getLogger(__name__)

def _ensure_valid_uuid(id_val: Any) -> str:
    """Ensures that point IDs submitted to Qdrant conform to standard RFC 4122 UUID format."""
    id_str = str(id_val)
    try:
        val = uuid.UUID(id_str)
        return str(val)
    except (ValueError, AttributeError):
        # Deterministically convert any arbitrary string/int to a valid UUIDv5
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, id_str))

class QdrantVectorStore(BaseVectorStore):
    def __init__(
        self,
        collection_name: str = "rag_enterprise_chunks",
        vector_size: int = 384,
        location: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._embedding_pipeline = None
        self._ranker = None

        # Connection strategy: URL/Host/Port or embedded local directory/in-memory
        env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
        DEMO_CLUSTER_URL = "https://6f3fe541-7e22-40bc-9792-b8a55f98ffb7.eu-central-1-0.aws.cloud.qdrant.io:6333"
        raw_url = url or os.getenv("QDRANT_URL") or os.getenv("QDRANT_ENDPOINT")
        if not raw_url or "cloud.qdrant.io/accounts" in raw_url:
            qdrant_url = DEMO_CLUSTER_URL
        else:
            qdrant_url = raw_url

        qdrant_api_key = api_key or os.getenv("QDRANT_API_KEY")
        if qdrant_api_key:
            qdrant_api_key = qdrant_api_key.strip()

        if qdrant_url:
            self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        elif host and port:
            self.client = QdrantClient(host=host, port=port, api_key=qdrant_api_key)
        else:
            if env in ("production", "prod"):
                raise RuntimeError(
                    "FATAL: QDRANT_URL is not configured in production environment. "
                    "Production must connect to Qdrant Cloud and cannot silently use an ephemeral local directory."
                )
            storage_loc = location or os.getenv("QDRANT_LOCATION", "./qdrant_storage")
            if storage_loc == ":memory:":
                self.client = QdrantClient(location=":memory:")
            else:
                os.makedirs(storage_loc, exist_ok=True)
                self.client = QdrantClient(path=storage_loc)

        self._ensure_collection()

    def _ensure_collection(self):
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=self.vector_size,
                    distance=qmodels.Distance.COSINE
                )
            )
            # Create payload indexes for high-speed tenant pre-filtering and document cascading
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="tenant_id",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="document_id",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="chunk_type",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
            except Exception as e:
                logger.debug(f"Payload index creation note: {e}")

    def _build_filter(self, tenant_id: Optional[str] = None, filters: Optional[Dict[str, Any]] = None) -> Optional[qmodels.Filter]:
        conditions = []
        if tenant_id:
            conditions.append(
                qmodels.FieldCondition(
                    key="tenant_id",
                    match=qmodels.MatchValue(value=tenant_id)
                )
            )
        if filters:
            for k, v in filters.items():
                conditions.append(
                    qmodels.FieldCondition(
                        key=k,
                        match=qmodels.MatchValue(value=v)
                    )
                )
        if not conditions:
            return None
        return qmodels.Filter(must=conditions)

    def add_documents(
        self,
        tenant_id: str,
        document_id: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]]
    ) -> List[str]:
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Mismatch in chunks ({len(chunks)}) and embeddings ({len(embeddings)}) length."
            )

        points = []
        point_ids = []

        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            raw_id = chunk.get("id") or f"{document_id}_{idx}"
            chunk_uuid = _ensure_valid_uuid(f"{tenant_id}:{document_id}:{raw_id}")
            point_ids.append(chunk_uuid)

            payload = {
                "tenant_id": tenant_id,
                "document_id": document_id,
                "chunk_id": chunk_uuid,
                "chunk_index": chunk.get("chunk_index", idx),
                "page": chunk.get("page", 1),
                "type": chunk.get("type", "text"),
                "text": chunk.get("text", ""),
                "summary": chunk.get("summary"),
                "source": chunk.get("source", "Unknown"),
                "filename": chunk.get("filename", "Unknown"),
                "image_path": chunk.get("image_path")
            }

            points.append(
                qmodels.PointStruct(
                    id=chunk_uuid,
                    vector=emb,
                    payload=payload
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        return point_ids

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        tenant_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        # Flatten query embedding if a 2D array or list of lists was passed
        flat_query = np.array(query_embedding).flatten().tolist()
        q_filter = self._build_filter(tenant_id, filters)
        search_res = self.client.query_points(
            collection_name=self.collection_name,
            query=flat_query,
            query_filter=q_filter,
            limit=top_k,
            with_payload=True
        )

        results = []
        for hit in search_res.points:
            results.append({
                "index": str(hit.id),
                "distance": float(hit.score),
                "metadata": hit.payload
            })
        return results

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        top_k: int = 5,
        tenant_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        rr_k: int = 60
    ) -> List[Dict[str, Any]]:
        fetch_k = max(top_k * 3, 20)
        dense_results = self.search(
            query_embedding=query_embedding,
            top_k=fetch_k,
            tenant_id=tenant_id,
            filters=filters
        )

        # Build sparse scoring over candidate space with complete pagination
        q_filter = self._build_filter(tenant_id, filters)
        all_points = []
        next_offset = None

        while True:
            scroll_res, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=q_filter,
                limit=1000,
                offset=next_offset,
                with_payload=True
            )
            all_points.extend(scroll_res)
            if next_offset is None or not scroll_res:
                break
        if not all_points:
            return []

        tokenized_corpus = [p.payload.get("text", "").lower().split() for p in all_points]
        point_ids = [str(p.id) for p in all_points]
        bm25 = BM25Okapi(tokenized_corpus)

        tokenized_query = query_text.lower().split()
        bm25_scores = bm25.get_scores(tokenized_query)
        sparse_top_indices = np.argsort(bm25_scores)[::-1][:fetch_k]

        rrf_scores = {}
        payload_map = {str(p.id): p.payload for p in all_points}

        for rank, res in enumerate(dense_results):
            pid = res["index"]
            rrf_scores[pid] = rrf_scores.get(pid, 0.0) + (1.0 / (rr_k + rank + 1))

        for rank, s_idx in enumerate(sparse_top_indices):
            pid = point_ids[s_idx]
            rrf_scores[pid] = rrf_scores.get(pid, 0.0) + (1.0 / (rr_k + rank + 1))

        sorted_pids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]

        results = []
        for pid in sorted_pids:
            results.append({
                "index": pid,
                "distance": float(rrf_scores[pid]),
                "metadata": payload_map.get(pid, {})
            })
        return results

    def delete_document(self, document_id: str, tenant_id: Optional[str] = None) -> bool:
        conditions = [
            qmodels.FieldCondition(
                key="document_id",
                match=qmodels.MatchValue(value=document_id)
            )
        ]
        if tenant_id:
            conditions.append(
                qmodels.FieldCondition(
                    key="tenant_id",
                    match=qmodels.MatchValue(value=tenant_id)
                )
            )
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(must=conditions)
            )
        )
        return True

    @property
    def embedding_pipeline(self):
        if self._embedding_pipeline is None:
            from src.rag.embedding import EmbeddingPipeline
            self._embedding_pipeline = EmbeddingPipeline()
        return self._embedding_pipeline

    def init_reranker(self):
        if self._ranker is None and Ranker is not None:
            try:
                self._ranker = Ranker()
            except Exception as e:
                logger.warning(f"Could not initialize FlashRank reranker: {e}")
                self._ranker = None

    def rerank(self, query_text: str, candidates: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        self.init_reranker()
        if not self._ranker or not candidates:
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
            reranked_passages = self._ranker.rerank(rerank_req)

            rerank_dict = {str(p["id"]): p["score"] for p in reranked_passages}

            reranked_candidates = []
            for c in candidates:
                idx = str(c["index"])
                if idx in rerank_dict:
                    c_copy = dict(c)
                    c_copy["distance"] = float(rerank_dict[idx])
                    reranked_candidates.append(c_copy)

            reranked_candidates.sort(key=lambda x: x["distance"], reverse=True)
            return reranked_candidates[:top_k]
        except Exception as e:
            logger.warning(f"Reranking failed in Qdrant store, returning original candidates: {e}")
            return candidates[:top_k]

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        use_hybrid: bool = True,
        use_rerank: bool = True,
        tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        # Fast exit if collection is empty to prevent loading heavy ML weights or hanging on Render
        try:
            coll_info = self.client.get_collection(self.collection_name)
            points_count = getattr(coll_info, "points_count", 0) or getattr(coll_info, "indexed_vectors_count", 0) or 0
            if points_count == 0:
                logger.info(f"Qdrant collection '{self.collection_name}' has 0 points. Skipping embedding model load.")
                return []
        except Exception as coll_err:
            logger.debug(f"Could not verify collection points count: {coll_err}")

        candidate_count = top_k * 3 if use_rerank else top_k
        query_emb = self.embedding_pipeline.model.encode([query_text]).tolist()

        if use_hybrid:
            candidates = self.hybrid_search(
                query_text=query_text,
                query_embedding=query_emb,
                top_k=candidate_count,
                tenant_id=tenant_id
            )
        else:
            candidates = self.search(
                query_embedding=query_emb,
                top_k=candidate_count,
                tenant_id=tenant_id
            )

        if use_rerank:
            return self.rerank(query_text, candidates, top_k=top_k)

        return candidates[:top_k]
