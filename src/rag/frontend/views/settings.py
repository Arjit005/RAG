"""Page 8: Settings foundation."""
import streamlit as st
from src.rag.frontend.components import render_page_header

def render_settings():
    render_page_header("Settings & Preferences", "Configure retrieval parameters, models, and active tenant context.")

    st.markdown('<div class="section-title">Model & Retrieval Parameters</div>', unsafe_allow_html=True)
    
    with st.container(border=True):
        st.session_state["settings_model"] = st.selectbox(
            "Primary LLM Inference Model:",
            ["qwen/qwen3.6-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "groq/compound-mini"],
            index=0
        )
        
        st.session_state["settings_top_k"] = st.slider(
            "Retrieved Candidates (Top-K):",
            min_value=1,
            max_value=10,
            value=st.session_state.get("settings_top_k", 5)
        )
        
        c1, c2 = st.columns(2)
        with c1:
            st.session_state["settings_hybrid"] = st.toggle(
                "Enable Hybrid Search (BM25 + Dense)",
                value=st.session_state.get("settings_hybrid", True),
                help="Combines sparse keyword search with dense vector embeddings using Reciprocal Rank Fusion."
            )
        with c2:
            st.session_state["settings_rerank"] = st.toggle(
                "Enable FlashRank Cross-Encoder Re-ranking",
                value=st.session_state.get("settings_rerank", True),
                help="Re-ranks candidate chunks using FlashRank cross-encoder for relevance."
            )

    st.markdown('<div class="section-title">Tenant & Authentication Scope</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.text_input("Active Tenant ID:", value="default-tenant", disabled=True, help="Enterprise isolation boundary.")
        st.caption("Cross-tenant filtering is enforced natively at the PostgreSQL and Qdrant levels.")
