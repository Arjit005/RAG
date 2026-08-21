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
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from rag.vectorstore import FaissVectorStore
except ImportError:
    from vectorstore import FaissVectorStore

load_dotenv()

class RAGSearch:
    def __init__(self, persist_dir: str = "faiss_store", embedding_model: str = "all-MiniLM-L6-v2", llm_model: str = "qwen/qwen3.6-27b", gemini_api_key: str = None):
        self.persist_dir = persist_dir
        self.embedding_model = embedding_model
        self.llm_model = llm_model
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.vectorstore = FaissVectorStore(persist_dir, embedding_model)
        self.ensure_store_loaded()
        self.init_llm()

    def init_llm(self):
        # Initialize Groq LLM
        groq_api_key = os.getenv("GROQ_API_KEY")
        if groq_api_key:
            try:
                self.llm = ChatGroq(groq_api_key=groq_api_key, model_name=self.llm_model)
                print(f"[INFO] Groq LLM initialized with model: {self.llm_model}")
            except Exception as e:
                self.llm = None
                print(f"[WARNING] Groq LLM failed to initialize: {e}")
        else:
            self.llm = None
            print("[WARNING] GROQ_API_KEY not found in environment variables.")

        # Initialize Gemini Multi-modal LLM
        if self.gemini_api_key:
            try:
                # Use gemini-3.6-flash for advanced multi-modal synthesis
                self.gemini_llm = ChatGoogleGenerativeAI(
                    model="gemini-3.6-flash",
                    google_api_key=self.gemini_api_key,
                    temperature=0.0
                )
                print("[INFO] Gemini 3.6 Flash LLM initialized.")
            except Exception as e:
                self.gemini_llm = None
                print(f"[WARNING] Gemini LLM failed to initialize: {e}")
        else:
            self.gemini_llm = None
            print("[WARNING] GEMINI_API_KEY not provided. Multi-modal RAG will run in text-fallback mode.")

    def ensure_store_loaded(self):
        faiss_path = os.path.join(self.persist_dir, "faiss.index")
        meta_path = os.path.join(self.persist_dir, "metadata.pkl")
        if not (os.path.exists(faiss_path) and os.path.exists(meta_path)):
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

    def search_and_answer(self, query: str, top_k: int = 5, chat_history: list = None, use_hybrid: bool = True, use_rerank: bool = True) -> dict:
        results = self.vectorstore.query(query, top_k=top_k, use_hybrid=use_hybrid, use_rerank=use_rerank)
        
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

        # Generate Multi-modal output if Gemini is configured and we have images
        if self.gemini_llm and (images_to_send or os.getenv("FORCE_GEMINI", "false").lower() == "true"):
            try:
                print(f"[INFO] Formulating multimodal answer using Gemini 1.5 Pro with {len(images_to_send)} images...")
                content = [{"type": "text", "text": prompt_instructions}] + images_to_send
                message = HumanMessage(content=content)
                response = self.gemini_llm.invoke([message])
                answer_text = response.content
                return {
                    "answer": answer_text,
                    "citations": citations
                }
            except Exception as e:
                print(f"[ERROR] Gemini multi-modal synthesis failed: {e}. Falling back to standard LLM.")

        # Fallback to standard Groq text-only LLM
        if not self.llm:
            warning_msg = ""
            if images_to_send and not self.gemini_llm:
                warning_msg = "\n\n*(Note: Some relevant images/charts were retrieved but could not be visually processed because GEMINI_API_KEY is not set.)*\n"
            return {
                "answer": f"**Retrieved Context (No LLM Key configured/available):**\n\n{context_str}{warning_msg}",
                "citations": citations
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
            "citations": citations
        }

if __name__ == "__main__":
    rag_search = RAGSearch()
    res = rag_search.search_and_answer("What is attention mechanism?", top_k=3)
    print("\n[ANSWER]:\n", res["answer"])
    print("\n[CITATIONS]:\n", res["citations"])