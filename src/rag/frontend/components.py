"""
Reusable UI component renderers for the Premium Light design system.
Includes:
- Page Header
- KPI / Metric Card
- Status Badge
- Citation / Evidence Box
- Empty State View
"""

import streamlit as st
from typing import Optional, Dict, Any


def render_page_header(title: str, subtitle: Optional[str] = None):
    """Renders a standardized page header with consistent typography."""
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def render_kpi_card(label: str, value: Any, subtitle: Optional[str] = None, badge_text: Optional[str] = None, badge_type: str = "neutral"):
    """Renders an enterprise KPI stat card."""
    badge_html = f'<span class="status-badge badge-{badge_type}" style="float: right;">{badge_text}</span>' if badge_text else ""
    sub_html = f'<div class="kpi-subtitle">{subtitle}</div>' if subtitle else ""
    
    html = f"""
    <div class="kpi-container">
        {badge_html}
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {sub_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_status_badge(text: str, badge_type: str = "neutral") -> str:
    """Returns HTML for a status badge ('success', 'warning', 'error', 'info', 'neutral')."""
    return f'<span class="status-badge badge-{badge_type}">{text}</span>'


def render_citation_box(
    source: str,
    page: int,
    snippet: str,
    score: Optional[float] = None,
    chunk_type: str = "text",
    image_path: Optional[str] = None
):
    """Renders a clean citation box separating evidence from AI generated responses."""
    badge_type = "info" if chunk_type == "text" else ("warning" if chunk_type == "table" else "success")
    type_label = chunk_type.upper()
    score_html = f'<span style="font-size: 0.8rem; color: #64748B; margin-left: auto;">Score: {score:.4f}</span>' if score is not None else ""
    
    html = f"""
    <div class="citation-box">
        <div class="citation-header">
            <span class="status-badge badge-neutral">📄 {source}</span>
            <span class="status-badge badge-neutral">Page {page}</span>
            <span class="status-badge badge-{badge_type}">{type_label}</span>
            {score_html}
        </div>
        <div class="citation-snippet">{snippet}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
    
    if chunk_type == "image" and image_path:
        import os
        if os.path.exists(image_path):
            st.image(image_path, caption=f"Extracted image from {source} (Page {page})", use_container_width=True)


def render_empty_state(title: str, description: str, icon: str = "📂"):
    """Renders an empty state placeholder with clean borders."""
    html = f"""
    <div class="empty-state">
        <div class="empty-state-icon">{icon}</div>
        <div class="empty-state-title">{title}</div>
        <div class="empty-state-desc">{description}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
