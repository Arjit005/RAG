"""
Centralized design tokens and global CSS styles for the Premium Light design system.
Adheres strictly to enterprise SaaS guidelines:
- Canvas: #F7F9FC
- Surface: #FFFFFF
- Sidebar: #F1F5F9
- Text Primary: #172B4D
- Text Secondary: #64748B
- Primary Action: #2563EB
- Primary Hover: #1D4ED8
- Borders: #E2E8F0
- Semantic Status: Success #16A34A, Warning #D97706, Error #DC2626, Info #0284C7
"""

GLOBAL_CSS = """
<style>
/* CSS Reset and Font Stack */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #172B4D;
}

/* Background canvas */
.stApp {
    background-color: #F7F9FC;
}

/* Sidebar styling */
[data-testid="stSidebar"] {
    background-color: #F1F5F9;
    border-right: 1px solid #E2E8F0;
}

[data-testid="stSidebar"] hr {
    margin: 1rem 0;
    border-color: #E2E8F0;
}

/* Global Card Container */
.enterprise-card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.enterprise-card:hover {
    border-color: #CBD5E1;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
}

/* Headers */
.page-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: #172B4D;
    margin-bottom: 0.25rem;
    letter-spacing: -0.02em;
}

.page-subtitle {
    font-size: 0.95rem;
    color: #64748B;
    margin-bottom: 1.5rem;
    line-height: 1.4;
}

.section-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #172B4D;
    margin-top: 1rem;
    margin-bottom: 0.75rem;
}

/* Badges */
.status-badge {
    display: inline-flex;
    align-items: center;
    padding: 0.2rem 0.55rem;
    font-size: 0.75rem;
    font-weight: 600;
    border-radius: 6px;
    line-height: 1;
}

.badge-success {
    background-color: #DCFCE7;
    color: #166534;
    border: 1px solid #BBF7D0;
}

.badge-warning {
    background-color: #FEF3C7;
    color: #92400E;
    border: 1px solid #FDE68A;
}

.badge-error {
    background-color: #FEE2E2;
    color: #991B1B;
    border: 1px solid #FECACA;
}

.badge-info {
    background-color: #E0F2FE;
    color: #075985;
    border: 1px solid #BAE6FD;
}

.badge-neutral {
    background-color: #F1F5F9;
    color: #475569;
    border: 1px solid #E2E8F0;
}

/* Citation & Evidence Card */
.citation-box {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #2563EB;
    border-radius: 8px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.75rem;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.citation-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
}

.citation-snippet {
    font-size: 0.88rem;
    color: #334155;
    line-height: 1.5;
    background-color: #F8FAFC;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    border: 1px solid #EDF2F7;
    margin-top: 0.4rem;
}

/* KPI / Metric Cards */
.kpi-container {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.kpi-label {
    font-size: 0.8rem;
    font-weight: 500;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
}

.kpi-value {
    font-size: 1.75rem;
    font-weight: 700;
    color: #172B4D;
    line-height: 1.1;
}

.kpi-subtitle {
    font-size: 0.8rem;
    color: #64748B;
    margin-top: 0.35rem;
}

/* Empty State Box */
.empty-state {
    text-align: center;
    padding: 2.5rem 1.5rem;
    background-color: #FFFFFF;
    border: 1px dashed #CBD5E1;
    border-radius: 10px;
    margin: 1rem 0;
}

.empty-state-icon {
    font-size: 2.2rem;
    color: #94A3B8;
    margin-bottom: 0.5rem;
}

.empty-state-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #172B4D;
    margin-bottom: 0.25rem;
}

.empty-state-desc {
    font-size: 0.9rem;
    color: #64748B;
    max-width: 420px;
    margin: 0 auto 1rem auto;
}

/* Upload Dropzone Styling (Phase F4.1) */
.upload-dropzone-header {
    border: 2px dashed #CBD5E1;
    border-radius: 12px;
    background-color: #FFFFFF;
    padding: 2rem 1.5rem;
    text-align: center;
    margin-bottom: 1rem;
    transition: all 0.2s ease-in-out;
}

.upload-dropzone-header:hover {
    border-color: #2563EB;
    background-color: #F8FAFC;
}

.upload-dropzone-icon {
    font-size: 2.75rem;
    color: #2563EB;
    margin-bottom: 0.5rem;
    line-height: 1;
}

.upload-dropzone-title {
    font-size: 1.15rem;
    font-weight: 600;
    color: #172B4D;
    margin-bottom: 0.25rem;
}

.upload-dropzone-subtitle {
    font-size: 0.875rem;
    color: #64748B;
    margin-bottom: 0.5rem;
}

.upload-dropzone-specs {
    font-size: 0.775rem;
    color: #94A3B8;
    display: flex;
    justify-content: center;
    gap: 1rem;
    margin-top: 0.5rem;
}

/* File Staging Card */
.staged-file-card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.staged-file-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.staged-file-name {
    font-weight: 600;
    color: #172B4D;
    font-size: 0.9rem;
}

.staged-file-meta {
    font-size: 0.8rem;
    color: #64748B;
}

/* Button & Input styling refinements */
button[kind="primary"] {
    background-color: #2563EB !important;
    border-color: #2563EB !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}

button[kind="primary"]:hover {
    background-color: #1D4ED8 !important;
    border-color: #1D4ED8 !important;
}

button[kind="secondary"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    color: #172B4D !important;
    border-radius: 8px !important;
}

button[kind="secondary"]:hover {
    background-color: #F8FAFC !important;
    border-color: #CBD5E1 !important;
}
</style>
"""
