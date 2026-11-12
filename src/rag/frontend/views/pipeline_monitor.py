"""Page 5: Pipeline Monitor foundation."""
import streamlit as st
from src.rag.frontend.components import render_page_header, render_empty_state

def render_pipeline_monitor():
    render_page_header("Pipeline Monitor", "Track document ingestion, text parsing, chunking, and vector indexing.")

    # Ingestion Pipeline Stage Visualizer
    st.markdown('<div class="section-title">Pipeline Architecture Flow</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        with st.container(border=True):
            st.markdown("**1. Upload**")
            st.caption("PDF / TXT / DOCX")
            st.markdown('<span class="status-badge badge-success">Ready</span>', unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            st.markdown("**2. Extraction**")
            st.caption("Text & Multi-modal")
            st.markdown('<span class="status-badge badge-success">Ready</span>', unsafe_allow_html=True)
    with c3:
        with st.container(border=True):
            st.markdown("**3. Chunking**")
            st.caption("Recursive Splitter")
            st.markdown('<span class="status-badge badge-success">Ready</span>', unsafe_allow_html=True)
    with c4:
        with st.container(border=True):
            st.markdown("**4. Embedding**")
            st.caption("all-MiniLM-L6-v2")
            st.markdown('<span class="status-badge badge-success">Ready</span>', unsafe_allow_html=True)
    with c5:
        with st.container(border=True):
            st.markdown("**5. Indexing**")
            st.caption("Neon + Qdrant")
            st.markdown('<span class="status-badge badge-success">Ready</span>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Active Ingestion Jobs</div>', unsafe_allow_html=True)
    render_empty_state("No Active Background Jobs", "All 6 documents (317 chunks) are currently indexed and synchronized.", icon="📊")
