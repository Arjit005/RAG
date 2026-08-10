import os
import sys
from pathlib import Path
import streamlit as st

# Setup sys.path for internal imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from rag.search import RAGSearch
    from rag.dataloader import load_all_documents
except ImportError:
    from search import RAGSearch
    from dataloader import load_all_documents

# Page configuration
st.set_page_config(
    page_title="RAG Intelligence Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #94a3b8;
        margin-bottom: 1.5rem;
    }
    .citation-card {
        background-color: #1e293b;
        border-left: 4px solid #6366f1;
        padding: 0.75rem 1rem;
        border-radius: 0.375rem;
        margin-bottom: 0.75rem;
    }
    .badge-source {
        background-color: #312e81;
        color: #c7d2fe;
        font-size: 0.75rem;
        padding: 0.2rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: 600;
    }
    .badge-page {
        background-color: #065f46;
        color: #a7f3d0;
        font-size: 0.75rem;
        padding: 0.2rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

if "rag_engine" not in st.session_state:
    st.session_state.rag_engine = None

# Header
st.markdown('<div class="main-header">⚡ Document Intelligence RAG Engine</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Ask questions across your PDFs, TXT files, and documents with instant source citations.</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("⚙️ Control Panel")
    
    # Model Selection
    model_choice = st.selectbox(
        "Select Groq LLM Model:",
        ["llama-3.3-70b-versatile", "gemma2-9b-it", "llama3-8b-8192"],
        index=0
    )
    
    top_k_val = st.slider("Retrieved Chunks (Top-K):", min_value=1, max_value=10, value=5)
    
    st.subheader("🔍 Retrieval Settings")
    use_hybrid = st.toggle("Hybrid Search (BM25 + FAISS)", value=True, help="Combines sparse keyword search with dense vector embeddings using Reciprocal Rank Fusion.")
    use_rerank = st.toggle("FlashRank Cross-Encoder Re-ranking", value=True, help="Re-ranks retrieved candidates using a Cross-Encoder for maximum relevance.")
    
    st.divider()
    
    # File Uploader
    st.subheader("📁 Upload Documents")
    uploaded_files = st.file_uploader(
        "Add PDF, TXT, CSV, or DOCX files to your knowledge base:",
        type=["pdf", "txt", "csv", "docx", "xlsx", "json"],
        accept_multiple_files=True
    )
    
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    if uploaded_files:
        if st.button("📥 Save & Index Uploaded Files", use_container_width=True):
            with st.spinner("Saving and indexing documents..."):
                saved_count = 0
                for file in uploaded_files:
                    # Create subfolder depending on extension
                    ext = file.name.split(".")[-1].lower()
                    subfolder = data_dir / (f"{ext}_files" if ext in ["txt", "csv", "json"] else ext)
                    subfolder.mkdir(parents=True, exist_ok=True)
                    
                    file_path = subfolder / file.name
                    with open(file_path, "wb") as f:
                        f.write(file.getbuffer())
                    saved_count += 1
                
                # Rebuild FAISS Index
                engine = RAGSearch(llm_model=model_choice)
                engine.rebuild_index()
                st.session_state.rag_engine = engine
                st.success(f"Successfully uploaded and indexed {saved_count} file(s)!")
    
    if st.button("🔄 Rebuild Vector Index", use_container_width=True):
        with st.spinner("Rebuilding FAISS index from data/ directory..."):
            engine = RAGSearch(llm_model=model_choice)
            engine.rebuild_index()
            st.session_state.rag_engine = engine
            st.success("Vector store rebuilt successfully!")
            
    st.divider()
    
    # List Existing Documents
    st.subheader("📚 Indexed Documents")
    existing_docs = list(data_dir.glob("**/*.*"))
    if existing_docs:
        for d in existing_docs[:10]:
            st.caption(f"• `{d.name}`")
        if len(existing_docs) > 10:
            st.caption(f"*...and {len(existing_docs) - 10} more files*")
    else:
        st.info("No documents found in data/ directory.")
        
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Initialize RAG Engine lazily
if st.session_state.rag_engine is None or st.session_state.rag_engine.llm_model != model_choice:
    st.session_state.rag_engine = RAGSearch(llm_model=model_choice)

# Display Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Display Citations if available
        citations = message.get("citations", [])
        if citations:
            with st.expander("📚 View Source Citations & References", expanded=False):
                for cit in citations:
                    st.markdown(
                        f"""<div class="citation-card">
                        <span class="badge-source">📄 {cit['source']}</span> 
                        <span class="badge-page">Page {cit['page']}</span>
                        <span style="font-size: 0.8rem; color: #94a3b8; margin-left: 0.5rem;">Score: {cit['distance']}</span>
                        <div style="margin-top: 0.5rem; font-size: 0.9rem; color: #cbd5e1;">{cit['snippet']}</div>
                        </div>""",
                        unsafe_allow_html=True
                    )

# User Chat Input
if prompt := st.chat_input("Ask a question about your documents..."):
    # Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate Assistant Response
    with st.chat_message("assistant"):
        with st.spinner("Searching document index and formulating answer..."):
            res = st.session_state.rag_engine.search_and_answer(
                query=prompt,
                top_k=top_k_val,
                chat_history=st.session_state.messages[:-1],
                use_hybrid=use_hybrid,
                use_rerank=use_rerank
            )
            
            answer = res.get("answer", "No answer generated.")
            citations = res.get("citations", [])
            
            st.markdown(answer)
            
            if citations:
                with st.expander("📚 View Source Citations & References", expanded=False):
                    for cit in citations:
                        st.markdown(
                            f"""<div class="citation-card">
                            <span class="badge-source">📄 {cit['source']}</span> 
                            <span class="badge-page">Page {cit['page']}</span>
                            <span style="font-size: 0.8rem; color: #94a3b8; margin-left: 0.5rem;">Score: {cit['distance']}</span>
                            <div style="margin-top: 0.5rem; font-size: 0.9rem; color: #cbd5e1;">{cit['snippet']}</div>
                            </div>""",
                            unsafe_allow_html=True
                        )

    # Save Assistant Message
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "citations": citations
    })
