# UI Phase F3.1: Tenant Authorization Security Verification Report

**Audit Date:** November 11, 2026  
**Auditor / Security Architect:** Senior Product Designer, Streamlit Frontend Architect & QA Engineer  
**Project:** RAG Intelligence — Enterprise AI Research Platform  
**Target:** Read-Only Adversarial Security Verification of Tenant Authorization & Data Exposure  
**Status:** AUDIT COMPLETE — CRITICAL AUTHORIZATION VULNERABILITY CONFIRMED — GATE HALTED  

---

## 1. Authentication Architecture Inspection

A static and dynamic code audit was conducted across [src/rag/api.py](file:///c:/Users/Dell/Downloads/RAG/src/rag/api.py), [src/rag/frontend/api_client.py](file:///c:/Users/Dell/Downloads/RAG/src/rag/frontend/api_client.py), and [src/rag/db/models.py](file:///c:/Users/Dell/Downloads/RAG/src/rag/db/models.py):

### 1.1 Findings:
1. **Absence of Caller Identity / Authentication:**
   - The FastAPI backend currently has **no authentication middleware, JWT validation, API key verification, or session management**.
   - Although the database schema includes a `User` model with `tenant_id`, `email`, `hashed_password`, and `role`, **no endpoints exist to authenticate users, issue tokens, or verify user identity**.
2. **Current `get_authorized_tenant` Implementation:**
   ```python
   def get_authorized_tenant(
       x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
       db: Session = Depends(get_db)
   ) -> str:
       tenant_id = x_tenant_id or "default-tenant"
       tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
       if not tenant:
           raise HTTPException(status_code=403, detail="Access denied")
       return tenant_id
   ```
   - **Critical Vulnerability (CWE-287 / CWE-639 - Insecure Direct Object Reference / Missing Authentication):**
     Authorization relies solely on the client-supplied HTTP header `X-Tenant-ID`. The server checks whether the tenant exists in PostgreSQL, but **does not verify whether the caller is authenticated or authorized to act on behalf of that tenant**.

---

## 2. Adversarial Tenant Authorization Test Results

Adversarial security tests were executed using an isolated test database fixture:

| Test Case | Scenario / Payload | Expected Secure Behavior | Actual Observed Result | Status |
| :--- | :--- | :---: | :---: | :---: |
| **1. Unauthenticated Request** | `GET /api/documents` (No headers) | `HTTP 401 Unauthorized` | `HTTP 200 OK` (Defaults to `default-tenant`) | **FAIL (Vulnerable)** |
| **2. Invalid Credentials** | `GET /api/documents` (`Authorization: Bearer invalid`) | `HTTP 401 Unauthorized` | `HTTP 200 OK` (Token completely ignored) | **FAIL (Vulnerable)** |
| **3. Legitimate Tenant A Access** | `GET /api/documents` (`X-Tenant-ID: default-tenant`) | `HTTP 200 OK` (Tenant A records) | `HTTP 200 OK` (Tenant A records) | **PASS** |
| **4. Header Spoofing (Tenant B)** | `GET /api/documents` (`X-Tenant-ID: isolated-tenant`) | `HTTP 403 Forbidden` | `HTTP 200 OK` (Returns Tenant B's documents!) | **CRITICAL FAIL** |
| **5. Cross-Tenant Document Access**| `GET /api/documents/doc-iso/chunks` (`X-Tenant-ID: default-tenant`) | `HTTP 404 Not Found` | `HTTP 404 Not Found` | **PASS** |
| **6. Cross-Tenant Chunk Access** | `GET /api/documents/doc-iso/chunks` (`X-Tenant-ID: isolated-tenant`) | `HTTP 403 Forbidden` without identity | `HTTP 200 OK` (Returns Tenant B chunks) | **FAIL (Vulnerable)** |
| **7. User Without Tenant Membership**| User requesting unassociated tenant | `HTTP 403 Forbidden` | *Not Applicable* (No user auth implemented) | **UNTESTABLE (Gap)** |
| **8. Valid Tenant B Access** | Legitimate user of Tenant B | `HTTP 200 OK` | `HTTP 200 OK` | **PASS** |
| **9. Nonexistent Tenant ID** | `GET /api/documents` (`X-Tenant-ID: fake-tenant-999`) | `HTTP 403 Forbidden` | `HTTP 403 Forbidden` ("Access denied") | **PASS** |
| **10. Metrics Global Exposure** | `GET /api/metrics/summary` (`X-Tenant-ID: isolated-tenant`) | Only Tenant metrics | Returns `"total_tenants": 3` | **MEDIUM FAIL** |

---

## 3. Metrics & Sensitive Data Exposure Assessment

1. **Information Leakage in `/api/metrics/summary`:**
   - In [src/rag/api.py](file:///c:/Users/Dell/Downloads/RAG/src/rag/api.py), the summary endpoint calculates:
     ```python
     total_tenants = db.query(Tenant).count()
     ```
   - Returning `total_tenants` leaks global multi-tenant platform sizing and infrastructure statistics to ordinary tenants.
   - **Remediation:** Remove `total_tenants` from the tenant-scoped summary endpoint or restrict it strictly to a `SystemAdmin` role.
2. **Document & Chunk Queries:**
   - Relational filtering (`filter(Document.tenant_id == tenant_id)`) correctly prevents cross-tenant record leakage *assuming* `tenant_id` is trusted.
   - Because `tenant_id` is currently read from an untrusted client header, an attacker knowing or guessing another tenant's ID can exfiltrate their document metadata.

---

## 4. Warning Classification (39 Warnings in Regression Suite)

All 39 warnings produced during the pytest run were inspected and categorized:

| Warning Category | Occurrences | Source File / Dependency | Severity | Analysis & Remediation |
| :--- | :---: | :--- | :---: | :--- |
| **`datetime.utcnow()` Deprecation** | **31** | `src/rag/db/models.py:45,58,72,73,96,113,114` & SQLAlchemy | **Low** | Python 3.12+ deprecates `datetime.datetime.utcnow()` in favor of timezone-aware `datetime.datetime.now(datetime.UTC)`. Works currently; update defaults before Python 3.14. |
| **Pydantic V2 Configuration Warnings** | **3** | `src/rag/api.py:103,117,142` (`class Config`) | **Low** | Pydantic v2.0 deprecated nested `class Config: from_attributes = True` in favor of `model_config = ConfigDict(from_attributes=True)`. Minor forward-compatibility fix. |
| **Pydantic Field Key Warning** | **1** | `src/rag/api.py:75` (`Field(example=...)`) | **Low** | Pydantic v2 deprecated `example=...` in favor of `json_schema_extra={"example": ...}`. |
| **Qdrant Local Payload Index Warning** | **1** | `src/rag/qdrant_store.py:64` | **Low** | Local Qdrant client notes that non-text payload indexes have no effect in-process. Normal behavior for local Qdrant. |
| **AnyIO Pytest CallSpec2 Warning** | **1** | `.venv/Lib/site-packages/anyio/pytest_plugin.py:14` | **External** | Upstream third-party warning in `anyio`. No action required. |
| **Starlette TestClient Warning** | **1** | `.venv/Lib/site-packages/fastapi/testclient.py:1` | **External** | FastApi/Starlette internal test client warning. No action required. |
| **LangChain Community Sunset Warning** | **1** | `src/rag/dataloader.py:22` | **External** | Deprecation notice for `langchain-community` document loaders. |

---

## 5. Required Security Remediation Plan

To achieve true enterprise multi-tenancy before proceeding with document management (Phase F4):

1. **Implement Server-Side Authentication:**
   - Establish token-based (Bearer API Key or JWT) authentication.
   - For internal service-to-service communication between Streamlit and FastAPI, configure an internal API secret (`API_INTERNAL_SECRET`) or HMAC signature.
2. **Bind Tenant Context to Authenticated Identity:**
   - Replace untrusted `X-Tenant-ID` parsing with authenticated user/token extraction:
     ```python
     def get_authorized_tenant(
         auth_header: str = Depends(oauth2_scheme), # or API key header
         db: Session = Depends(get_db)
     ) -> str:
         user = verify_token_and_get_user(auth_header, db)
         if not user:
             raise HTTPException(status_code=401, detail="Invalid credentials")
         return user.tenant_id
     ```
3. **Redact Global Metrics:**
   - Remove `total_tenants` from `/api/metrics/summary`.

---

## 6. Security Decision & Gate Boundary

In adherence to Section 3 and Section 7:
- **Decision:** **CONDITIONAL HOLD ON PHASE F4**.
- The architectural gap is explicitly documented. The system cannot claim authenticated multi-tenant security while `X-Tenant-ID` is untrusted.
- No production application code or Neon database records have been modified.

Awaiting user review and authorization on the proposed authentication remediation plan.
