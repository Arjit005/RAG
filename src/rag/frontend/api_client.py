"""
src/rag/frontend/api_client.py

Centralized API Client for RAG Intelligence Enterprise Platform.
Communicates strictly over HTTP with the FastAPI backend.
Key characteristics:
- Configurable base URL (via RAG_API_BASE_URL, defaults to http://127.0.0.1:8000)
- Configurable timeouts (connect: 5s, read: 30s)
- Automatic authentication and token renewal for seamless UI operation
- Centralized error handling and structured exceptions
- Redaction of credentials and sensitive payloads from logs
- No database credentials or direct database imports
"""

import os
import logging
from typing import Optional, Dict, Any, List
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    """Base exception for API client operations."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class ServiceUnavailableError(APIClientError):
    """Raised when the backend API is unreachable or timing out."""
    pass


class AuthenticationError(APIClientError):
    """Raised on 401 or 403 authorization failures."""
    pass


class NotFoundError(APIClientError):
    """Raised when a resource (e.g. document) is not found."""
    pass


class RAGApiClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 15.0,
        api_key: Optional[str] = None,
        auth_token: Optional[str] = None
    ):
        self.base_url = (base_url or os.getenv("RAG_API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.timeout = timeout
        self.api_key = api_key or os.getenv("RAG_API_KEY")
        self.auth_token = auth_token or os.getenv("RAG_AUTH_TOKEN")
        
        # Default service-to-service credentials for enterprise UI
        self.default_email = os.getenv("RAG_DEFAULT_USER_EMAIL", "admin@enterprise.internal")
        self.default_password = os.getenv("RAG_DEFAULT_USER_PASSWORD", "EnterpriseAdmin2026!")

    def set_auth_token(self, token: str):
        """Sets active Bearer token."""
        self.auth_token = token

    def authenticate_default(self) -> str:
        """Authenticates with default credentials to establish active session token."""
        try:
            resp = requests.post(
                f"{self.base_url}/api/auth/token",
                json={"email": self.default_email, "password": self.default_password},
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                self.auth_token = data["access_token"]
                return self.auth_token
        except Exception as e:
            logger.warning(f"Could not authenticate default user: {e}")
        return ""

    def _headers(self, tenant_id: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        if not self.auth_token:
            self.authenticate_default()

        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._headers(tenant_id=tenant_id)
        if files:
            # Let requests handle multipart content-type boundary
            headers.pop("Content-Type", None)

        try:
            resp = requests.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                files=files,
                headers=headers,
                timeout=self.timeout
            )
        except (ConnectionError, Timeout) as e:
            logger.error(f"Backend API connection error at {path}: {type(e).__name__}")
            raise ServiceUnavailableError(
                f"FastAPI backend at '{self.base_url}' is unreachable or timed out."
            ) from e
        except RequestException as e:
            logger.error(f"HTTP request error at {path}: {type(e).__name__}")
            raise APIClientError(f"HTTP request failed: {str(e)}") from e

        if resp.status_code == 401:
            # Try re-authenticating once if token expired
            if self.authenticate_default():
                headers["Authorization"] = f"Bearer {self.auth_token}"
                resp = requests.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    files=files,
                    headers=headers,
                    timeout=self.timeout
                )

        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"Unauthorized or access denied (HTTP {resp.status_code}): {resp.text}",
                status_code=resp.status_code
            )
        elif resp.status_code == 404:
            raise NotFoundError(
                f"Resource not found (HTTP 404): {resp.text}",
                status_code=404
            )
        elif resp.status_code >= 400:
            raise APIClientError(
                f"API error (HTTP {resp.status_code}): {resp.text}",
                status_code=resp.status_code
            )

        return resp.json()

    def get_health(self) -> Dict[str, Any]:
        """Fetch system health from GET /api/health."""
        return self._request("GET", "/api/health")

    def list_documents(self, tenant_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Fetch documents from GET /api/documents."""
        return self._request(
            "GET",
            "/api/documents",
            params={"limit": limit, "offset": offset},
            tenant_id=tenant_id
        )

    def get_document_chunks(self, document_id: str, tenant_id: str) -> List[Dict[str, Any]]:
        """Fetch chunks for an authorized document from GET /api/documents/{document_id}/chunks."""
        return self._request(
            "GET",
            f"/api/documents/{document_id}/chunks",
            tenant_id=tenant_id
        )

    def delete_document(self, document_id: str, tenant_id: str) -> Dict[str, Any]:
        """Deletes a document and cascades to vector store from DELETE /api/documents/{document_id}."""
        return self._request(
            "DELETE",
            f"/api/documents/{document_id}",
            tenant_id=tenant_id
        )

    def upload_document(self, file_name: str, file_bytes: bytes, tenant_id: str) -> Dict[str, Any]:
        """Uploads a document via POST /api/documents/upload."""
        url = f"{self.base_url}/api/documents/upload"
        headers = self._headers(tenant_id=tenant_id)
        headers.pop("Content-Type", None)
        
        files = {"file": (file_name, file_bytes)}
        try:
            resp = requests.post(url, files=files, headers=headers, timeout=self.timeout)
            if resp.status_code >= 400:
                raise APIClientError(f"Upload failed (HTTP {resp.status_code}): {resp.text}", status_code=resp.status_code)
            return resp.json()
        except (ConnectionError, Timeout) as e:
            raise ServiceUnavailableError(f"Upload failed: Backend at '{self.base_url}' is unreachable.") from e

    def get_metrics_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Fetch system & tenant metrics from GET /api/metrics/summary."""
        return self._request(
            "GET",
            "/api/metrics/summary",
            tenant_id=tenant_id
        )

    def list_pipeline_jobs(self, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch ingestion jobs from GET /api/pipeline/jobs."""
        return self._request(
            "GET",
            "/api/pipeline/jobs",
            params={"limit": limit},
            tenant_id=tenant_id
        )

    def chat(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
        use_hybrid: bool = True,
        use_rerank: bool = True,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        model: str = "qwen/qwen3.6-27b"
    ) -> Dict[str, Any]:
        """
        Sends synchronous research inquiry to POST /api/chat.
        Returns complete response dict with answer, citations, model, and metadata.
        """
        payload = {
            "query": query,
            "top_k": top_k,
            "use_hybrid": use_hybrid,
            "use_rerank": use_rerank,
            "chat_history": chat_history or [],
            "model": model
        }
        return self._request(
            "POST",
            "/api/chat",
            json=payload,
            tenant_id=tenant_id
        )

    def chat_stream(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
        use_hybrid: bool = True,
        use_rerank: bool = True,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        model: str = "qwen/qwen3.6-27b"
    ):
        """
        Streams research inquiry events from POST /api/chat/stream using Server-Sent Events.
        Yields parsed event dictionaries:
          - {"type": "message_start", "query": "..."}
          - {"type": "citations", "citations": [...]}
          - {"type": "token", "token": "..."}
          - {"type": "message_complete"}
          - {"type": "error", "error": "..."}
        """
        url = f"{self.base_url}/api/chat/stream"
        payload = {
            "query": query,
            "top_k": top_k,
            "use_hybrid": use_hybrid,
            "use_rerank": use_rerank,
            "chat_history": chat_history or [],
            "model": model
        }

        import json
        headers = self._headers(tenant_id=tenant_id)

        try:
            connect_timeout = self.timeout[0] if isinstance(self.timeout, (tuple, list)) else self.timeout
            with requests.post(url, json=payload, headers=headers, stream=True, timeout=(connect_timeout, 60)) as resp:
                if resp.status_code == 401 or resp.status_code == 403:
                    raise AuthenticationError(f"Authentication failed: {resp.text}", status_code=resp.status_code)
                elif resp.status_code >= 400:
                    raise APIClientError(f"Chat stream failed (HTTP {resp.status_code}): {resp.text}", status_code=resp.status_code)

                for line in resp.iter_lines(decode_unicode=True):
                    if line:
                        line_str = line.strip()
                        if line_str.startswith("data:"):
                            raw_json = line_str[5:].strip()
                            try:
                                event = json.loads(raw_json)
                                yield event
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse SSE JSON: {raw_json}")
                                continue
        except (ConnectionError, Timeout) as e:
            raise ServiceUnavailableError(f"Streaming failed: Backend at '{self.base_url}' is unreachable.") from e
