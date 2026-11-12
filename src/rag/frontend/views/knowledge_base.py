"""
src/rag/frontend/views/knowledge_base.py

Page 3: Knowledge Base & Document Inventory view.
Fully integrated with FastAPI backend (RAGApiClient):
- Displays live documents from PostgreSQL with pagination and filename search
- Document details drawer/expander with metadata and chunk counts
- Authorized chunk inspection
- Drag-and-drop document upload with asynchronous background ingestion
- Explicit confirmation modal/button for document deletion
- Pure dynamic data: Zero hardcoded document lists
"""

import streamlit as st
from typing import Optional
from src.rag.frontend.components import render_page_header, render_empty_state
from src.rag.frontend.api_client import RAGApiClient, APIClientError, NotFoundError, ServiceUnavailableError


def get_api_client() -> RAGApiClient:
    if "api_client" not in st.session_state:
        st.session_state.api_client = RAGApiClient()
    return st.session_state.api_client


def render_knowledge_base():
    render_page_header("Knowledge Base", "Upload, inspect, and manage enterprise documents, metadata, and embeddings.")
    
    client = get_api_client()
    tenant_id = st.session_state.get("active_tenant_id", "default-tenant")

    tab1, tab2, tab3 = st.tabs(["📄 Document Inventory", "🔍 Document Inspector", "📤 Upload Documents"])

    # --- TAB 1: Document Inventory ---
    with tab1:
        st.markdown('<div class="section-title">Indexed Documents (Live from PostgreSQL)</div>', unsafe_allow_html=True)
        
        c1, c2 = st.columns([3, 1])
        with c1:
            search_query = st.text_input("Filter by filename:", placeholder="Search documents...", label_visibility="collapsed")
        with c2:
            if st.button("🔄 Refresh Documents", use_container_width=True):
                st.rerun()

        try:
            docs = client.list_documents(tenant_id=tenant_id, limit=100, offset=0)
            if search_query:
                docs = [d for d in docs if search_query.lower() in d["filename"].lower()]

            if not docs:
                render_empty_state(
                    "No Documents Found",
                    "There are currently no documents indexed in this tenant. Use the Upload tab to add enterprise files.",
                    icon="📁"
                )
            else:
                formatted_docs = []
                for d in docs:
                    formatted_docs.append({
                        "Document ID": d["id"][:12] + "...",
                        "Filename": d["filename"],
                        "Type": d["file_type"].upper(),
                        "Pages": d["page_count"],
                        "Chunks": d["chunk_count"],
                        "Status": d["status"].upper(),
                        "Uploaded At": d["created_at"][:19].replace("T", " ")
                    })
                st.dataframe(formatted_docs, use_container_width=True)
                st.caption(f"Showing {len(formatted_docs)} document(s) for tenant `{tenant_id}`.")
        except ServiceUnavailableError:
            st.error("FastAPI backend is currently offline. Please ensure the API service is running on port 8000.")
        except APIClientError as e:
            st.error(f"Error loading documents: {e.args[0]}")

    # --- TAB 2: Document Inspector & Chunks ---
    with tab2:
        st.markdown('<div class="section-title">Inspect Document & Chunks</div>', unsafe_allow_html=True)
        try:
            docs = client.list_documents(tenant_id=tenant_id, limit=100)
            if not docs:
                st.info("No documents available to inspect.")
            else:
                doc_options = {f"{d['filename']} ({d['id'][:8]}...)": d["id"] for d in docs}
                selected_label = st.selectbox("Select document to inspect:", list(doc_options.keys()))
                selected_doc_id = doc_options[selected_label]
                
                selected_doc = next((d for d in docs if d["id"] == selected_doc_id), None)
                if selected_doc:
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total Pages", selected_doc["page_count"])
                    with col2:
                        st.metric("Total Chunks", selected_doc["chunk_count"])
                    with col3:
                        st.metric("Content Hash", selected_doc["content_hash"][:10] + "...")
                    with col4:
                        st.metric("Status", selected_doc["status"].upper())

                    # Action buttons
                    st.divider()
                    del_col1, del_col2 = st.columns([4, 1])
                    with del_col2:
                        if st.button("🗑️ Delete Document", type="secondary", use_container_width=True):
                            st.session_state[f"confirm_delete_{selected_doc_id}"] = True

                    if st.session_state.get(f"confirm_delete_{selected_doc_id}"):
                        st.warning(f"Are you sure you want to permanently delete **{selected_doc['filename']}** and all associated vectors?")
                        c_yes, c_no = st.columns(2)
                        with c_yes:
                            if st.button("Yes, Delete Permanently", type="primary"):
                                try:
                                    client.delete_document(selected_doc_id, tenant_id=tenant_id)
                                    st.success(f"Document {selected_doc['filename']} deleted successfully.")
                                    st.session_state.pop(f"confirm_delete_{selected_doc_id}", None)
                                    st.rerun()
                                except APIClientError as e:
                                    st.error(f"Deletion failed: {e}")
                        with c_no:
                            if st.button("Cancel"):
                                st.session_state.pop(f"confirm_delete_{selected_doc_id}", None)
                                st.rerun()

                    # Chunk List
                    st.markdown("#### Document Chunks")
                    chunks = client.get_document_chunks(selected_doc_id, tenant_id=tenant_id)
                    for c in chunks[:20]:
                        with st.expander(f"Chunk #{c['chunk_index']} — Page {c['page_number']} ({c['chunk_type'].upper()})"):
                            st.caption(f"Chunk ID: `{c['id']}` | Qdrant Point ID: `{c['qdrant_point_id']}`")
                            st.markdown(f"> {c['content_text']}")
                    if len(chunks) > 20:
                        st.caption(f"*...showing first 20 of {len(chunks)} chunks*")
        except APIClientError as e:
            st.error(f"Error inspecting document: {e.args[0]}")

    # --- TAB 3: Upload Documents (Phase F4.1 Premium Drag & Drop) ---
    with tab3:
        st.markdown('<div class="section-title">Upload & Ingest Enterprise Documents</div>', unsafe_allow_html=True)
        
        # 1. Custom Hero Dropzone Card adhering to Premium Light Design Tokens
        dropzone_html = """
        <div class="upload-dropzone-header">
            <div class="upload-dropzone-icon">☁️</div>
            <div class="upload-dropzone-title">Drag & Drop your files here</div>
            <div class="upload-dropzone-subtitle">or click Browse Files below to upload documents to your knowledge base</div>
            <div class="upload-dropzone-specs">
                <span>📄 Supported Formats: <strong>PDF, TXT, CSV, DOCX, JSON</strong></span>
                <span>•</span>
                <span>⚖️ Max File Size: <strong>25 MB per file</strong></span>
            </div>
        </div>
        """
        st.markdown(dropzone_html, unsafe_allow_html=True)

        # 2. File Uploader supporting Drag & Drop and Browse Files
        uploaded_files = st.file_uploader(
            "Upload files",
            type=["pdf", "txt", "csv", "docx", "json"],
            accept_multiple_files=True,
            help="Drag files directly into this zone or click Browse Files to select from your device.",
            label_visibility="collapsed"
        )

        # File staging session state tracking for removal and sequential execution
        if "staged_uploads_removed" not in st.session_state:
            st.session_state.staged_uploads_removed = set()

        if uploaded_files:
            # Filter out files removed by individual user action
            active_files = [f for f in uploaded_files if f.name not in st.session_state.staged_uploads_removed]

            if not active_files:
                st.info("All staged files have been dismissed. Drag or browse new files to upload.")
            else:
                st.markdown(f"##### 📋 Staged for Ingestion ({len(active_files)} file{'s' if len(active_files) > 1 else ''})")

                # Validation & individual card rendering
                valid_files = []
                has_oversized = False

                for f in active_files:
                    f_size_mb = f.size / (1024 * 1024)
                    ext = f.name.split(".")[-1].upper() if "." in f.name else "UNKNOWN"
                    is_oversized = f.size > 25 * 1024 * 1024
                    if is_oversized:
                        has_oversized = True

                    card_col, action_col = st.columns([5, 1])
                    with card_col:
                        badge_type = "error" if is_oversized else "info"
                        status_note = " ⚠️ **Exceeds 25 MB limit**" if is_oversized else ""
                        st.markdown(
                            f"""
                            <div class="staged-file-card">
                                <div class="staged-file-info">
                                    <span style="font-size: 1.4rem;">📄</span>
                                    <div>
                                        <div class="staged-file-name">{f.name}</div>
                                        <div class="staged-file-meta">Format: <strong>{ext}</strong> | Size: <strong>{f_size_mb:.2f} MB</strong>{status_note}</div>
                                    </div>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    with action_col:
                        if st.button("✕ Remove", key=f"remove_file_{f.name}", use_container_width=True):
                            st.session_state.staged_uploads_removed.add(f.name)
                            st.rerun()

                    if not is_oversized:
                        valid_files.append(f)

                if has_oversized:
                    st.error("One or more staged files exceed the maximum 25 MB limit and will be skipped.")

                st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

                # Sequential Upload Action
                btn_col1, btn_col2 = st.columns([3, 1])
                with btn_col1:
                    upload_submitted = st.button(
                        f"🚀 Upload & Ingest {len(valid_files)} Document{'s' if len(valid_files) > 1 else ''}",
                        type="primary",
                        disabled=len(valid_files) == 0,
                        use_container_width=True
                    )
                with btn_col2:
                    if st.button("Clear All", use_container_width=True):
                        st.session_state.staged_uploads_removed.update([f.name for f in uploaded_files])
                        st.rerun()

                if upload_submitted and valid_files:
                    # Upload status container with distinct lifecycle states
                    upload_results_box = st.container()
                    with upload_results_box:
                        st.markdown("#### ⏳ Ingestion Execution Progress")
                        progress_bar = st.progress(0, text="Initializing sequential document transfer...")

                        success_count = 0
                        for idx, file_to_upload in enumerate(valid_files):
                            current_step = f"Uploading {idx + 1}/{len(valid_files)}: {file_to_upload.name}..."
                            progress_ratio = (idx) / len(valid_files)
                            progress_bar.progress(progress_ratio, text=current_step)

                            status_placeholder = st.empty()
                            status_placeholder.info(f"📤 **State: Uploading** — Sending `{file_to_upload.name}` to secure API gateway...")

                            try:
                                content_bytes = file_to_upload.getvalue()
                                res = client.upload_document(file_to_upload.name, content_bytes, tenant_id=tenant_id)
                                job_id = res.get("job_id", "N/A")

                                status_placeholder.success(
                                    f"✅ **State: Upload Accepted** — `{file_to_upload.name}` registered. "
                                    f"Job ID: `{job_id}`. Ingestion running asynchronously in background."
                                )
                                success_count += 1
                                # Dismiss from staged queue upon successful upload
                                st.session_state.staged_uploads_removed.add(file_to_upload.name)

                            except APIClientError as e:
                                status_placeholder.error(f"❌ **State: Failed** — Upload failed for `{file_to_upload.name}`: {e.args[0]}")
                            except Exception as ex:
                                status_placeholder.error(f"❌ **State: Failed** — Unexpected transfer error for `{file_to_upload.name}`: {str(ex)}")

                        final_ratio = 1.0
                        progress_bar.progress(final_ratio, text=f"Sequential upload complete: {success_count}/{len(valid_files)} accepted.")

                        if success_count > 0:
                            st.toast(f"Successfully scheduled {success_count} document(s) for ingestion!", icon="🚀")
                            st.caption("Tip: Monitor asynchronous extraction, embedding, and vector synchronization progress in the **Pipeline Monitor** or **Activity & Audit** tabs.")
        else:
            # Reset removed tracker when no files are staged in Streamlit uploader
            st.session_state.staged_uploads_removed = set()
