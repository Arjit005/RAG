import sys
import uuid

# Windows AppLocker/WDAC DLL block compatibility mock
class CompatMock:
    @staticmethod
    def uuid7():
        return uuid.uuid4()

class UUIDUtilsMock:
    compat = CompatMock()

sys.modules['uuid_utils'] = UUIDUtilsMock()
sys.modules['uuid_utils.compat'] = CompatMock()

import os
from pathlib import Path
import streamlit as st

# Setup sys.path for internal imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.frontend.styles import GLOBAL_CSS
from src.rag.frontend.views.overview import render_overview
from src.rag.frontend.views.chat import render_research_chat
from src.rag.frontend.views.knowledge_base import render_knowledge_base
from src.rag.frontend.views.retrieval_explorer import render_retrieval_explorer
from src.rag.frontend.views.pipeline_monitor import render_pipeline_monitor
from src.rag.frontend.views.system_health import render_system_health
from src.rag.frontend.views.activity_audit import render_activity_audit
from src.rag.frontend.views.settings import render_settings

# Page configuration
st.set_page_config(
    page_title="RAG Intelligence — Enterprise Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply Global Design System Styles
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Application Branding & Navigation Shell
with st.sidebar:
    st.markdown("""
        <div style="padding: 0.5rem 0 1rem 0;">
            <div style="font-size: 1.25rem; font-weight: 700; color: #172B4D; letter-spacing: -0.02em;">
                ⚡ RAG Intelligence
            </div>
            <div style="font-size: 0.8rem; color: #64748B; font-weight: 500;">
                Enterprise AI Research Platform
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    st.caption("WORKSPACE")
    nav_workspace = [
        "📊 Overview",
        "💬 Research Chat",
        "📚 Knowledge Base",
        "🔬 Retrieval Explorer",
        "📈 Pipeline Monitor",
    ]
    
    st.caption("OPERATIONS")
    nav_operations = [
        "🩺 System Health",
        "📋 Activity & Audit",
        "⚙️ Settings",
    ]
    
    # Combined Navigation Radio
    all_pages = nav_workspace + nav_operations
    selected_page = st.radio(
        "Navigation Menu",
        options=all_pages,
        label_visibility="collapsed",
        index=0
    )
    
    st.divider()
    
    # Active Environment Context
    st.markdown("""
        <div style="font-size: 0.75rem; color: #64748B;">
            <div><b>Environment:</b> Production</div>
            <div><b>Tenant:</b> default-tenant</div>
            <div><b>Cluster:</b> Neon AWS us-east-2</div>
        </div>
    """, unsafe_allow_html=True)

# Route to active view
if selected_page == "📊 Overview":
    render_overview()
elif selected_page == "💬 Research Chat":
    render_research_chat()
elif selected_page == "📚 Knowledge Base":
    render_knowledge_base()
elif selected_page == "🔬 Retrieval Explorer":
    render_retrieval_explorer()
elif selected_page == "📈 Pipeline Monitor":
    render_pipeline_monitor()
elif selected_page == "🩺 System Health":
    render_system_health()
elif selected_page == "📋 Activity & Audit":
    render_activity_audit()
elif selected_page == "⚙️ Settings":
    render_settings()
