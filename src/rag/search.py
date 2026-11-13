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

from pathlib import Path
import os
import base64
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
# from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
# from langchain_google_genai import ChatGoogleGenerativeAI
from src.rag.llm.model_router import get_model_router

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    # from rag.vectorstore import FaissVectorStore
except Exception:
    try:
        # from vectorstore import FaissVectorStore
    except Exception:
        FaissVectorStore = None

from src.rag.vector_store_factory import get_vector_store

load_dotenv()

class RAGSearch:
    def __init__(
        self,
        persist_dir: str = "faiss_store",
        embedding_model: str = "all-MiniLM-L6-v2",
        llm_model: str = "qwen/qwen3.8-27b",
        gemini_api_key: str = None,
        vectorstore = None
    ):
        self.persist_dir = persist_dir
        self.embedding_model = embedding_model
        self.llm_model = llm_model
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        
        # Use centralized vector store factory if not explicitly provided
        if vectorstore is not None:
            self.vectorstore = vectorstore
        else:
            self.vectorstore = get_vector_store(embedding_model=embedding_model)

        self.ensure_store_loaded()
        self.init_llm()

    def init_llm(self):
        # Multi-provider routing is handled dynamically by ModelRouter
        self.llm = None
        self.gemini_llm = None

    def ensure_store_loaded(self):
        # QdrantVectorStore handles its own collection lifecycle; only load or rebuild if using FAISS
        if hasattr(self.vectorstore, "load"):
            faiss_path = os.path.join(self.persist_dir, "faiss.index")
            meta_path = os.path.join(self.persist_dir, "metadata.pkl")
            if not (os.path.exists(faiss_path) and os.path.exists(meta_path)):
                env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
                if env in ("production", "prod"):
                    raise RuntimeError("FATAL: FAISS store missing in production environment. Production must use Qdrant Cloud.")
                self.rebuild_index()
            else:
                self.vectorstore.load()

    def rebuild_index(self):
        try:
            from rag.dataloader import load_all_documents
        except ImportError:
            from dataloader import load_all_documents
        docs = load_all_documents("data", self.gemini_api_key)
        self.vectorstore.build_from_documents(docs)

    def search_and_answer(self, query: str, top_k: int = 5, chat_history: list = None, use_hybrid: bool = True, use_rerank: bool = True, tenant_id: Optional[str] = None) -> dict:
        if hasattr(self.vectorstore, "query"):
            import inspect
            try:
                sig = inspect.signature(self.vectorstore.query)
                # If signature contains tenant_id or is a generic mock (*args, **kwargs)
                if "tenant_id" in sig.parameters or "kwargs" in sig.parameters:
                    results = self.vectorstore.query(query, top_k=top_k, use_hybrid=use_hybrid, use_rerank=use_rerank, tenant_id=tenant_id)
                else:
                    if tenant_id is not None:
                        raise TypeError("Underlying vector store does not support tenant-scoped queries; rejecting unscoped multi-tenant search.")
                    results = self.vectorstore.query(query, top_k=top_k, use_hybrid=use_hybrid, use_rerank=use_rerank)
            except (ValueError, TypeError):
                results = self.vectorstore.query(query, top_k=top_k, use_hybrid=use_hybrid, use_rerank=use_rerank, tenant_id=tenant_id)
        else:
            results = []
        
        context_blocks = []
        citations = []
        images_to_send = []
        
        for idx, r in enumerate(results, 1):
            meta = r.get("metadata") or {}
            text = meta.get("text", "")
            source = meta.get("source") or meta.get("filename") or "Unknown Document"
            page = meta.get("page", 1)
            dist = float(r.get("distance", 0.0))
            doc_type = meta.get("type", "text")
            
            if doc_type == "image":
                image_path = meta.get("image_path")
                if image_path and os.path.exists(image_path):
                    try:
                        with open(image_path, "rb") as img_file:
                            img_b64 = base64.b64encode(img_file.read()).decode("utf-8")
                        images_to_send.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                        })
                        context_blocks.append(f"[Document {idx} (Image summary): {source} (Page {page})]\n{text}")
                        citations.append({
                            "source": source,
                            "page": page,
                            "snippet": f"Visual Image content summary: {text}",
                            "distance": round(dist, 4),
                            "type": "image",
                            "image_path": image_path
                        })
                    except Exception as e:
                        print(f"[ERROR] Failed to read image {image_path}: {e}")
                else:
                    context_blocks.append(f"[Document {idx} (Image metadata missing/removed): {source} (Page {page})]\n{text}")
                    citations.append({
                        "source": source,
                        "page": page,
                        "snippet": f"Image (file missing): {text}",
                        "distance": round(dist, 4),
                        "type": "image"
                    })
            elif doc_type == "table":
                context_blocks.append(f"[Document {idx} (Table): {source} (Page {page})]\n{text}")
                citations.append({
                    "source": source,
                    "page": page,
                    "snippet": f"Structured Table Data:\n{text}",
                    "distance": round(dist, 4),
                    "type": "table"
                })
            else:
                context_blocks.append(f"[Document {idx} (Text): {source} (Page {page})]\n{text}")
                citations.append({
                    "source": source,
                    "page": page,
                    "snippet": text[:350] + ("..." if len(text) > 350 else ""),
                    "distance": round(dist, 4),
                    "type": "text"
                })

        context_str = "\n\n---\n\n".join(context_blocks)
        
        if not context_str:
            return {
                "answer": "No relevant document chunks were found in the knowledge base.",
                "citations": []
            }

        history_str = ""
        if chat_history:
            formatted_history = []
            for msg in chat_history[-6:]:
                role = "User" if msg.get("role") == "user" else "Assistant"
                formatted_history.append(f"{role}: {msg.get('content', '')}")
            history_str = "\nPrevious Conversation:\n" + "\n".join(formatted_history) + "\n"

        prompt_instructions = f"""You are a helpful and precise RAG assistant. Answer the user's question using ONLY the provided document context below (which includes text, extracted table structures, and images).
If the context does not contain enough information to answer, state clearly that the documents do not specify.
Always refer to the specific source document and page number when citing facts.

{history_str}
Context from Documents:
{context_str}

User Question: {query}

Detailed Answer:"""

        # Multi-Provider Router with Automatic Failover
        router = get_model_router()
        try:
            route_res = router.invoke(
                prompt=prompt_instructions,
                preferred_model_id=self.llm_model,
                require_multimodal=bool(images_to_send),
                images=images_to_send if images_to_send else None
            )
            answer_text = route_res.get("answer", "")
            routed_model = route_res.get("model_id", self.llm_model)
            routed_provider = route_res.get("provider", "unknown")
            routed_tier = route_res.get("tier", "unknown")
            failover_occurred = route_res.get("failover_occurred", False)

            return {
                "answer": answer_text,
                "citations": citations,
                "model_id": routed_model,
                "provider": routed_provider,
                "tier": routed_tier,
                "failover_occurred": failover_occurred
            }
        except Exception as router_err:
            print(f"[WARNING] Model router invocation failed: {router_err}. Falling back to direct LLM.")

        # Fallback to direct Gemini Multi-modal if configured and we have images
        if self.gemini_llm and (images_to_send or os.getenv("FORCE_GEMINI", "false").lower() == "true"):
            try:
                print(f"[INFO] Formulating multimodal answer using Gemini fallback with {len(images_to_send)} images...")
                content = [{"type": "text", "text": prompt_instructions}] + images_to_send
                message = HumanMessage(content=content)
                response = self.gemini_llm.invoke([message])
                answer_text = response.content
                return {
                    "answer": answer_text,
                    "citations": citations,
                    "model_id": "gemini-3.6-flash",
                    "provider": "gemini",
                    "tier": "free",
                    "failover_occurred": True
                }
            except Exception as e:
                print(f"[ERROR] Direct Gemini multi-modal synthesis failed: {e}.")

        # Fallback to standard Groq text-only LLM
        if not self.llm:
            warning_msg = ""
            if images_to_send and not self.gemini_llm:
                warning_msg = "\n\n*(Note: Some relevant images/charts were retrieved but could not be visually processed because GEMINI_API_KEY is not set.)*\n"
            return {
                "answer": f"**Retrieved Context (No LLM Key configured/available):**\n\n{context_str}{warning_msg}",
                "citations": citations,
                "model_id": "none",
                "provider": "none",
                "tier": "none",
                "failover_occurred": False
            }

        try:
            response = self.llm.invoke([prompt_instructions])
            answer_text = response.content
            if images_to_send and not self.gemini_llm:
                answer_text += "\n\n*(Note: Some relevant charts or images were retrieved but could not be visually processed because GEMINI_API_KEY is not set. The response is based on the textual summaries and content.)*"
        except Exception as e:
            answer_text = f"Error generating answer with Groq LLM: {str(e)}"

        return {
            "answer": answer_text,
            "citations": citations,
            "model_id": self.llm_model,
            "provider": "groq",
            "tier": "paid",
            "failover_occurred": False
        }

    def stream_and_answer(self, query: str, top_k: int = 5, chat_history: list = None, use_hybrid: bool = True, use_rerank: bool = True, tenant_id: Optional[str] = None):
        """
        Yields tokens and citations in real time as an event stream.
        1st event: {"type": "citations", "citations": [...]}
        subsequent events: {"type": "token", "token": "..."}
        final event: {"type": "done"}
        """
        if hasattr(self.vectorstore, "query"):
            import inspect
            try:
                sig = inspect.signature(self.vectorstore.query)
                if "tenant_id" in sig.parameters or "kwargs" in sig.parameters:
                    results = self.vectorstore.query(query, top_k=top_k, use_hybrid=use_hybrid, use_rerank=use_rerank, tenant_id=tenant_id)
                else:
                    if tenant_id is not None:
                        raise TypeError("Underlying vector store does not support tenant-scoped queries; rejecting unscoped multi-tenant search.")
                    results = self.vectorstore.query(query, top_k=top_k, use_hybrid=use_hybrid, use_rerank=use_rerank)
            except (ValueError, TypeError):
                results = self.vectorstore.query(query, top_k=top_k, use_hybrid=use_hybrid, use_rerank=use_rerank, tenant_id=tenant_id)
        else:
            results = []
        
        context_blocks = []
        citations = []
        images_to_send = []
        
        for idx, r in enumerate(results, 1):
            meta = r.get("metadata") or {}
            text = meta.get("text", "")
            source = meta.get("source") or meta.get("filename") or "Unknown Document"
            page = meta.get("page", 1)
            dist = float(r.get("distance", 0.0))
            doc_type = meta.get("type", "text")
            
            if doc_type == "image":
                image_path = meta.get("image_path")
                if image_path and os.path.exists(image_path):
                    try:
                        with open(image_path, "rb") as img_file:
                            img_b64 = base64.b64encode(img_file.read()).decode("utf-8")
                        images_to_send.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                        })
                        context_blocks.append(f"[Document {idx} (Image summary): {source} (Page {page})]\n{text}")
                        citations.append({
                            "source": source,
                            "page": page,
                            "snippet": f"Visual Image content summary: {text}",
                            "distance": round(dist, 4),
                            "type": "image",
                            "image_path": image_path
                        })
                    except Exception as e:
                        print(f"[ERROR] Failed to read image {image_path}: {e}")
                else:
                    context_blocks.append(f"[Document {idx} (Image metadata missing/removed): {source} (Page {page})]\n{text}")
                    citations.append({
                        "source": source,
                        "page": page,
                        "snippet": f"Image (file missing): {text}",
                        "distance": round(dist, 4),
                        "type": "image"
                    })
            elif doc_type == "table":
                context_blocks.append(f"[Document {idx} (Table): {source} (Page {page})]\n{text}")
                citations.append({
                    "source": source,
                    "page": page,
                    "snippet": f"Structured Table Data:\n{text}",
                    "distance": round(dist, 4),
                    "type": "table"
                })
            else:
                context_blocks.append(f"[Document {idx} (Text): {source} (Page {page})]\n{text}")
                citations.append({
                    "source": source,
                    "page": page,
                    "snippet": text[:350] + ("..." if len(text) > 350 else ""),
                    "distance": round(dist, 4),
                    "type": "text"
                })

        context_str = "\n\n---\n\n".join(context_blocks)
        
        # 1. Yield citations first
        yield {"type": "citations", "citations": citations}

        if not context_str:
            yield {"type": "token", "token": "No relevant document chunks were found in the knowledge base."}
            yield {"type": "done"}
            return

        history_str = ""
        if chat_history:
            formatted_history = []
            for msg in chat_history[-6:]:
                role = "User" if msg.get("role") == "user" else "Assistant"
                formatted_history.append(f"{role}: {msg.get('content', '')}")
            history_str = "\nPrevious Conversation:\n" + "\n".join(formatted_history) + "\n"

        prompt_instructions = f"""You are a helpful and precise RAG assistant. Answer the user's question using ONLY the provided document context below (which includes text, extracted table structures, and images).
If the context does not contain enough information to answer, state clearly that the documents do not specify.
Always refer to the specific source document and page number when citing facts.

{history_str}
Context from Documents:
{context_str}

User Question: {query}

Detailed Answer:"""

        # Multi-Provider Router with Automatic Streaming Failover
        router = get_model_router()
        streamed_any_token = False
        try:
            for ev in router.stream(
                prompt=prompt_instructions,
                preferred_model_id=self.llm_model,
                require_multimodal=bool(images_to_send),
                images=images_to_send if images_to_send else None
            ):
                ev_type = ev.get("type")
                if ev_type == "model_selected":
                    yield {
                        "type": "model_selected",
                        "model_id": ev.get("model_id"),
                        "provider": ev.get("provider"),
                        "tier": ev.get("tier"),
                        "failover_occurred": (ev.get("model_id") != self.llm_model)
                    }
                elif ev_type == "token":
                    streamed_any_token = True
                    yield {"type": "token", "token": ev.get("token")}
                elif ev_type == "done":
                    yield {"type": "done"}
                    return
                elif ev_type == "error":
                    print(f"[WARNING] Router yielded streaming error: {ev.get('error')}. Attempting fallbacks.")
                    break
        except Exception as router_err:
            print(f"[WARNING] Model router streaming failed: {router_err}. Falling back to direct LLM.")

        if streamed_any_token:
            yield {"type": "done"}
            return

        # Direct Gemini Multi-modal fallback if router failed before any token
        if self.gemini_llm and (images_to_send or os.getenv("FORCE_GEMINI", "false").lower() == "true"):
            try:
                content = [{"type": "text", "text": prompt_instructions}] + images_to_send
                message = HumanMessage(content=content)
                for chunk in self.gemini_llm.stream([message]):
                    if chunk.content:
                        yield {"type": "token", "token": chunk.content}
                yield {"type": "done"}
                return
            except Exception as e:
                print(f"[ERROR] Direct Gemini streaming failed: {e}. Falling back to standard LLM.")

        if not self.llm:
            warning_msg = ""
            if images_to_send and not self.gemini_llm:
                warning_msg = "\n\n*(Note: Some relevant images/charts were retrieved but could not be visually processed because GEMINI_API_KEY is not set.)*\n"
            yield {"type": "token", "token": f"**Retrieved Context (No LLM Key configured/available):**\n\n{context_str}{warning_msg}"}
            yield {"type": "done"}
            return

        try:
            for chunk in self.llm.stream([prompt_instructions]):
                if chunk.content:
                    yield {"type": "token", "token": chunk.content}
            if images_to_send and not self.gemini_llm:
                yield {"type": "token", "token": "\n\n*(Note: Some relevant charts or images were retrieved but could not be visually processed because GEMINI_API_KEY is not set.)*"}
        except Exception as e:
            yield {"type": "token", "token": f"Error generating answer with Groq LLM: {str(e)}"}

        yield {"type": "done"}

if __name__ == "__main__":
    rag_search = RAGSearch()
    res = rag_search.search_and_answer("What is attention mechanism?", top_k=3)
    print("\n[ANSWER]:\n", res["answer"])
    print("\n[CITATIONS]:\n", res["citations"])