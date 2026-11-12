"""Page 4: Retrieval Explorer foundation."""
import streamlit as st
from src.rag.frontend.components import render_page_header, render_empty_state

def render_retrieval_explorer():
    render_page_header("Retrieval Explorer", "Inspect dense embeddings, BM25 sparse scores, and RRF rank fusion.")

    query = st.text_input("Test Retrieval Query:", value="What is attention mechanism?")
    c1, c2, c3 = st.columns(3)
    with c1:
        top_k = st.slider("Top Candidates:", 1, 10, 5)
    with c2:
        use_hybrid = st.checkbox("Hybrid (Dense + BM25)", value=True)
    with c3:
        use_rerank = st.checkbox("FlashRank Re-ranking", value=True)

    if st.button("🔍 Execute Search Trace", type="primary"):
        with st.spinner("Executing retrieval trace..."):
            rag_engine = st.session_state.get("rag_engine")
            if rag_engine is None:
                try:
                    from src.rag.search import RAGSearch
                    rag_engine = RAGSearch()
                    st.session_state.rag_engine = rag_engine
                except Exception as e:
                    st.error(f"Failed to load RAG engine: {e}")
                    return

            res = rag_engine.search_and_answer(query, top_k=top_k, use_hybrid=use_hybrid, use_rerank=use_rerank)
            citations = res.get("citations", [])

            st.markdown('<div class="section-title">Retrieved Candidates</div>', unsafe_allow_html=True)
            for idx, cit in enumerate(citations, 1):
                with st.container(border=True):
                    st.markdown(f"**Rank #{idx}: {cit.get('source')}** (Page {cit.get('page')})")
                    st.caption(f"Score / Distance: {cit.get('distance')} | Type: {cit.get('type')}")
                    st.markdown(f"> {cit.get('snippet')}")
    else:
        render_empty_state("Ready to Trace Retrieval", "Enter a query and click 'Execute Search Trace' to inspect retrieved chunks and rank fusion.", icon="🔬")
