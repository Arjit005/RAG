"""
Page 2: Research Chat — Premium Evidence-Backed AI Research Workspace.
Strictly communicates via RAGApiClient with FastAPI backend over HTTP.
Features:
- Real-time token streaming with SSE
- Dedicated evidence expanders with authentic citations & confidence metrics
- Suggested inquiry starters for empty states
- Configurable retrieval parameters (Top-K, Hybrid search, Cross-Encoder reranking)
- Conversation history reset & copy answer support
- Graceful error states and zero internal credentials exposure
"""

import os
import time
import streamlit as st
from typing import List, Dict, Any

from src.rag.frontend.api_client import (
    RAGApiClient,
    APIClientError,
    AuthenticationError,
    ServiceUnavailableError,
)
from src.rag.frontend.components import (
    render_page_header,
    render_citation_box,
    render_empty_state,
    render_status_badge,
)

SUGGESTED_PROMPTS = [
    "What is the self-attention mechanism and how does it compute representations?",
    "Explain the architecture differences between dot-product and additive attention.",
    "What are the key object detection findings and proposal mechanisms discussed?",
    "Summarize the supervised vs unsupervised learning fundamentals from the notes.",
]


def render_research_chat():
    render_page_header(
        "AI Research Workspace",
        "Evidence-grounded multi-modal intelligence across enterprise documents."
    )

    api_client: RAGApiClient = st.session_state.get("api_client")
    if not api_client:
        api_client = RAGApiClient()
        st.session_state.api_client = api_client

    tenant_id = st.session_state.get("current_tenant", "default-tenant")

    # 1. Workspace Controls & Settings Toolbar
    with st.expander("⚙️ Retrieval Parameters & Session Controls", expanded=False):
        c1, c2, c3, c4 = st.columns([1.5, 1.5, 1.5, 1.5])
        with c1:
            top_k = st.slider("Top Chunks (Top-K)", min_value=1, max_value=15, value=st.session_state.get("chat_top_k", 5), key="chat_top_k")
        with c2:
            use_hybrid = st.toggle("Hybrid Search (Dense + BM25)", value=st.session_state.get("chat_hybrid", True), key="chat_hybrid")
        with c3:
            use_rerank = st.toggle("FlashRank Cross-Encoder", value=st.session_state.get("chat_rerank", True), key="chat_rerank")
        with c4:
            st.write("")
            if st.button("🗑️ Clear Conversation", use_container_width=True):
                st.session_state.messages = []
                st.rerun()

    # 2. Initialize Session Messages
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 3. Empty State with Interactive Starters
    if not st.session_state.messages:
        render_empty_state(
            "Start an AI Research Inquiry",
            "Submit a research inquiry across your tenant's indexed documents. Responses are synthesized in real time with verbatim citations and confidence metrics.",
            icon="💬"
        )
        st.markdown("##### 💡 Suggested Research Inquiries")
        cols = st.columns(2)
        for i, prompt_suggestion in enumerate(SUGGESTED_PROMPTS):
            col_target = cols[i % 2]
            with col_target:
                if st.button(prompt_suggestion, key=f"starter_prompt_{i}", use_container_width=True):
                    _execute_chat_inquiry(
                        prompt_suggestion,
                        api_client=api_client,
                        tenant_id=tenant_id,
                        top_k=top_k,
                        use_hybrid=use_hybrid,
                        use_rerank=use_rerank,
                    )
                    st.rerun()
    else:
        # 4. Render Conversation History
        for msg_idx, msg in enumerate(st.session_state.messages):
            role = msg["role"]
            with st.chat_message(role):
                st.markdown(msg["content"])

                # Render evidence drawer for assistant responses
                citations = msg.get("citations", [])
                if citations:
                    with st.expander(f"📚 Verified Evidence & Citations ({len(citations)} sources)", expanded=False):
                        for cit_idx, cit in enumerate(citations):
                            render_citation_box(
                                source=cit.get("source", "Document"),
                                page=cit.get("page", 1),
                                snippet=cit.get("snippet", ""),
                                score=cit.get("distance"),
                                chunk_type=cit.get("type", "text"),
                                image_path=cit.get("image_path"),
                            )

    # 5. User Input Handler
    if prompt := st.chat_input("Ask a question across your indexed documents..."):
        _execute_chat_inquiry(
            prompt,
            api_client=api_client,
            tenant_id=tenant_id,
            top_k=top_k,
            use_hybrid=use_hybrid,
            use_rerank=use_rerank,
        )
        st.rerun()


def _execute_chat_inquiry(
    prompt: str,
    api_client: RAGApiClient,
    tenant_id: str,
    top_k: int,
    use_hybrid: bool,
    use_rerank: bool
):
    """
    Executes streaming research inquiry via FastAPI backend.
    Updates st.session_state.messages with user query and assistant response.
    """
    # Append user prompt immediately
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Render conversational turn live
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        status_placeholder = st.empty()
        status_placeholder.info("⚡ Authenticating and retrieving supporting evidence...")

        full_answer = ""
        citations: List[Dict[str, Any]] = []
        start_time = time.time()
        first_token_time = None

        try:
            # Stream from FastAPI SSE endpoint
            for event in api_client.chat_stream(
                query=prompt,
                tenant_id=tenant_id,
                top_k=top_k,
                use_hybrid=use_hybrid,
                use_rerank=use_rerank,
                chat_history=st.session_state.messages[:-1]
            ):
                event_type = event.get("type")

                if event_type == "message_start":
                    status_placeholder.info("🔍 Retrieving dense vectors & sparse BM25 scores...")

                elif event_type == "citations":
                    citations = event.get("citations", [])
                    status_placeholder.empty()

                elif event_type == "token":
                    if first_token_time is None:
                        first_token_time = time.time()
                    token = event.get("token", "")
                    full_answer += token
                    answer_placeholder.markdown(full_answer + "▌")

                elif event_type == "message_complete":
                    status_placeholder.empty()

                elif event_type == "error":
                    status_placeholder.error(f"Inquiry Error: {event.get('error')}")

            # Finalize rendered text
            status_placeholder.empty()
            if not full_answer:
                full_answer = "No response generated by the retrieval pipeline."
            answer_placeholder.markdown(full_answer)

            # Render supporting evidence cards
            if citations:
                with st.expander(f"📚 Verified Evidence & Citations ({len(citations)} sources)", expanded=True):
                    for cit in citations:
                        render_citation_box(
                            source=cit.get("source", "Document"),
                            page=cit.get("page", 1),
                            snippet=cit.get("snippet", ""),
                            score=cit.get("distance"),
                            chunk_type=cit.get("type", "text"),
                            image_path=cit.get("image_path")
                        )

            # Append to session history
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_answer,
                "citations": citations
            })

        except AuthenticationError as e:
            status_placeholder.error("🔒 Authentication required or session token expired. Please re-authenticate.")
        except ServiceUnavailableError as e:
            status_placeholder.error("⚠️ RAG Intelligence backend is temporarily unreachable. Please ensure FastAPI is running.")
        except APIClientError as e:
            status_placeholder.error(f"Error executing research inquiry: {e.message}")
        except Exception as e:
            status_placeholder.error(f"Unexpected inquiry failure: {str(e)}")
