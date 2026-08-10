import sys
from pathlib import Path
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from rag.vectorstore import FaissVectorStore
except ImportError:
    from vectorstore import FaissVectorStore

load_dotenv()

class RAGSearch:
    def __init__(self, persist_dir: str = "faiss_store", embedding_model: str = "all-MiniLM-L6-v2", llm_model: str = "llama-3.3-70b-versatile"):
        self.persist_dir = persist_dir
        self.embedding_model = embedding_model
        self.llm_model = llm_model
        self.vectorstore = FaissVectorStore(persist_dir, embedding_model)
        self.ensure_store_loaded()
        self.init_llm()

    def init_llm(self):
        groq_api_key = os.getenv("GROQ_API_KEY")
        if groq_api_key:
            self.llm = ChatGroq(groq_api_key=groq_api_key, model_name=self.llm_model)
            print(f"[INFO] Groq LLM initialized with model: {self.llm_model}")
        else:
            self.llm = None
            print("[WARNING] GROQ_API_KEY not found in environment variables.")

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
        docs = load_all_documents("data")
        self.vectorstore.build_from_documents(docs)

    def search_and_answer(self, query: str, top_k: int = 5, chat_history: list = None, use_hybrid: bool = True, use_rerank: bool = True) -> dict:
        results = self.vectorstore.query(query, top_k=top_k, use_hybrid=use_hybrid, use_rerank=use_rerank)
        
        context_blocks = []
        citations = []
        
        for idx, r in enumerate(results, 1):
            meta = r.get("metadata") or {}
            text = meta.get("text", "")
            source = meta.get("source") or meta.get("filename") or "Unknown Document"
            page = meta.get("page", 1)
            dist = float(r.get("distance", 0.0))
            
            context_blocks.append(f"[Document {idx}: {source} (Page {page})]\n{text}")
            citations.append({
                "source": source,
                "page": page,
                "snippet": text[:350] + ("..." if len(text) > 350 else ""),
                "distance": round(dist, 4)
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

        prompt = f"""You are a helpful and precise RAG assistant. Answer the user's question using ONLY the provided document context below.
If the context does not contain enough information to answer, state clearly that the documents do not specify.
Always refer to the specific source document and page number when citing facts.

{history_str}
Context from Documents:
{context_str}

User Question: {query}

Detailed Answer:"""

        if not self.llm:
            return {
                "answer": f"**Retrieved Context (No Groq API Key set):**\n\n{context_str}",
                "citations": citations
            }

        try:
            response = self.llm.invoke([prompt])
            answer_text = response.content
        except Exception as e:
            answer_text = f"Error generating answer with Groq LLM: {str(e)}"

        return {
            "answer": answer_text,
            "citations": citations
        }

# Example usage
if __name__ == "__main__":
    rag_search = RAGSearch()
    res = rag_search.search_and_answer("What is attention mechanism?", top_k=3)
    print("\n[ANSWER]:\n", res["answer"])
    print("\n[CITATIONS]:\n", res["citations"])