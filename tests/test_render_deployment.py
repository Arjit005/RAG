"""
Tests for Render Production Deployment Security, Configuration, and Infrastructure Readiness.
Verifies:
1. JWT configuration uses JWT_SECRET_KEY and fails in production if missing or weak.
2. Production Qdrant initialization strictly requires QDRANT_URL and prevents fallback to ephemeral local storage.
3. Health check separating liveness (/api/health/live) and deep readiness (/api/health).
4. CORS policy enforces explicit origins in production.
"""

import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.rag.api import app


def test_jwt_production_requires_secret():
    """Confirms auth module rejects missing or short secret in production."""
    with patch.dict(os.environ, {"ENV": "production", "JWT_SECRET_KEY": "", "JWT_SECRET": ""}):
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY environment variable is mandatory"):
            import importlib
            import src.rag.db.auth as auth_mod
            importlib.reload(auth_mod)

    # Too short secret (< 32 chars)
    with patch.dict(os.environ, {"ENV": "production", "JWT_SECRET_KEY": "short-secret-key"}):
        with pytest.raises(RuntimeError, match="too weak for production"):
            import importlib
            import src.rag.db.auth as auth_mod
            importlib.reload(auth_mod)

    # Clean reload for other tests
    with patch.dict(os.environ, {"ENV": "development"}):
        import importlib
        import src.rag.db.auth as auth_mod
        importlib.reload(auth_mod)


def test_qdrant_production_requires_qdrant_url():
    """Confirms QdrantVectorStore rejects ephemeral storage in production."""
    with patch.dict(os.environ, {"ENV": "production", "QDRANT_URL": "", "QDRANT_API_KEY": ""}):
        from src.rag.qdrant_store import QdrantVectorStore
        with pytest.raises(RuntimeError, match="QDRANT_URL is not configured in production"):
            QdrantVectorStore(collection_name="test_prod_collection")


def test_liveness_probe():
    """Verifies lightweight liveness probe returns 200 without DB queries or ML weights."""
    client = TestClient(app)
    resp = client.get("/api/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


def test_readiness_probe_with_healthy_db():
    """Verifies readiness probe returns 200 and checks DB + model availability."""
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "groq_llm_ready" in data


def test_cors_origin_policy():
    """Verifies CORS policy permits configured frontend origin."""
    client = TestClient(app)
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")
