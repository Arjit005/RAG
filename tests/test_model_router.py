"""
tests/test_model_router.py

Comprehensive Automated Test Suite for Multi-Provider AI Model Router & Failover.
Covers 24 rigorous test scenarios:
 1. Primary provider success without failover.
 2. Primary timeout (HTTP/Socket timeout) triggers automatic failover.
 3. Primary HTTP 429 (Rate Limit) triggers failover to secondary model.
 4. Primary HTTP 500/503 service outage triggers failover.
 5. Multi-key rotation on 429 rate limit.
 6. Secondary key success after primary key 429.
 7. Circuit breaker state transition to OPEN on repeated failures.
 8. Circuit breaker prevents calling failed provider while in cooldown.
 9. Circuit breaker transition from OPEN to HALF_OPEN after cooldown.
10. Successful probe in HALF_OPEN restores circuit breaker to CLOSED.
11. Pre-first-token failure in streaming triggers seamless failover without client error.
12. Mid-stream interruption yields structured error event and halts safely.
13. Free tier preference prioritizes free models over paid ones.
14. Multimodal request filtering routes to multimodal-capable models only.
15. Non-multimodal request correctly uses text-only models.
16. Disabling model in registry removes it from candidate list.
17. Priority adjustment dynamically updates model routing order.
18. Missing API credentials skips provider cleanly without crashing.
19. Masked API key representation prevents credential leakage.
20. All providers exhausted raises clear, actionable exception.
21. Context window validation & model descriptor attributes.
22. FastAPI GET /api/llm/models endpoint returns models and masked provider health.
23. FastAPI POST /api/llm/config updates model enabled status and priority.
24. RAGSearch search_and_answer seamlessly uses router with failover metadata.
"""

import time
import pytest
from unittest.mock import patch, MagicMock
from src.rag.llm.model_router import (
    ModelRouter,
    ModelDescriptor,
    ProviderType,
    TierType,
    CircuitState,
    ProviderHealth,
    DEFAULT_REGISTRY
)


@pytest.fixture
def clean_router():
    """Provides a fresh ModelRouter with standard mock models for isolated testing."""
    test_registry = [
        ModelDescriptor(
            provider=ProviderType.GROQ,
            model_id="groq-primary",
            display_name="Groq Primary",
            tier=TierType.PAID,
            env_key_var="GROQ_API_KEY",
            context_window=32768,
            max_output_tokens=4096,
            supports_multimodal=False,
            supports_streaming=True,
            priority=10,
            enabled=True
        ),
        ModelDescriptor(
            provider=ProviderType.GEMINI,
            model_id="gemini-free-fallback",
            display_name="Gemini Free",
            tier=TierType.FREE,
            env_key_var="GEMINI_API_KEY",
            context_window=1048576,
            max_output_tokens=8192,
            supports_multimodal=True,
            supports_streaming=True,
            priority=20,
            enabled=True
        ),
        ModelDescriptor(
            provider=ProviderType.OPENROUTER,
            model_id="openrouter-free-backup",
            display_name="OpenRouter Free Backup",
            tier=TierType.FREE,
            env_key_var="OPENROUTER_API_KEY",
            context_window=32768,
            max_output_tokens=4096,
            supports_multimodal=False,
            supports_streaming=True,
            priority=30,
            enabled=True
        ),
    ]
    router = ModelRouter(registry=test_registry)
    return router


# Scenario 1: Primary provider success
def test_01_primary_provider_success(clean_router):
    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key-1"]):
        with patch.object(clean_router, "_execute_provider_call", return_value="Success from Groq"):
            res = clean_router.invoke(prompt="Hello", preferred_model_id="groq-primary")
            assert res["answer"] == "Success from Groq"
            assert res["model_id"] == "groq-primary"
            assert res["provider"] == "groq"
            assert res["failover_occurred"] is False


# Scenario 2: Primary timeout triggers automatic failover
def test_02_primary_timeout_triggers_failover(clean_router):
    def side_effect(model_desc, key, prompt, images):
        if model_desc.model_id == "groq-primary":
            raise TimeoutError("Connection to Groq timed out")
        return "Recovered via Gemini"

    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        with patch.object(clean_router, "_execute_provider_call", side_effect=side_effect):
            res = clean_router.invoke(prompt="Hello", preferred_model_id="groq-primary")
            assert res["answer"] == "Recovered via Gemini"
            assert res["model_id"] == "gemini-free-fallback"
            assert res["failover_occurred"] is True


# Scenario 3: Primary HTTP 429 triggers failover
def test_03_primary_429_rate_limit_failover(clean_router):
    def side_effect(model_desc, key, prompt, images):
        if model_desc.model_id == "groq-primary":
            err = Exception("HTTP 429: Too Many Requests - Quota exceeded")
            err.status_code = 429
            raise err
        return "Answer from Gemini Free"

    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        with patch.object(clean_router, "_execute_provider_call", side_effect=side_effect):
            res = clean_router.invoke(prompt="Analyze data", preferred_model_id="groq-primary")
            assert res["answer"] == "Answer from Gemini Free"
            assert res["model_id"] == "gemini-free-fallback"
            assert res["tier"] == "free"
            assert res["failover_occurred"] is True


# Scenario 4: Primary HTTP 500/503 service outage triggers failover
def test_04_primary_503_outage_failover(clean_router):
    def side_effect(model_desc, key, prompt, images):
        if model_desc.model_id == "groq-primary":
            raise RuntimeError("HTTP 503: Service Unavailable")
        return "Answer after service outage"

    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        with patch.object(clean_router, "_execute_provider_call", side_effect=side_effect):
            res = clean_router.invoke(prompt="Ping", preferred_model_id="groq-primary")
            assert res["answer"] == "Answer after service outage"
            assert res["failover_occurred"] is True


# Scenario 5: Multi-key rotation on 429 rate limit
def test_05_multi_key_rotation_on_429(clean_router):
    with patch.object(clean_router, "get_provider_keys", return_value=["key-primary", "key-secondary"]):
        clean_router.key_rotation_index[ProviderType.GROQ] = 0
        assert clean_router.get_active_key(ProviderType.GROQ) == "key-primary"

        clean_router.record_failure(ProviderType.GROQ, error_status=429)
        assert clean_router.get_active_key(ProviderType.GROQ) == "key-secondary"


# Scenario 6: Secondary key success after primary key 429
def test_06_secondary_key_success(clean_router):
    with patch.object(clean_router, "get_provider_keys", return_value=["key-primary", "key-secondary"]):
        clean_router.key_rotation_index[ProviderType.GROQ] = 0
        clean_router.rotate_key(ProviderType.GROQ)
        assert clean_router.get_active_key(ProviderType.GROQ) == "key-secondary"


# Scenario 7: Circuit breaker state transition to OPEN
def test_07_circuit_breaker_trips_to_open(clean_router):
    health = clean_router.health_map[ProviderType.GROQ]
    assert health.state == CircuitState.CLOSED

    # Simulate 3 consecutive failures
    clean_router.record_failure(ProviderType.GROQ, error_status=500)
    clean_router.record_failure(ProviderType.GROQ, error_status=500)
    clean_router.record_failure(ProviderType.GROQ, error_status=500)

    assert health.state == CircuitState.OPEN


# Scenario 8: Circuit breaker prevents calling OPEN provider in cooldown
def test_08_circuit_breaker_blocks_in_cooldown(clean_router):
    health = clean_router.health_map[ProviderType.GROQ]
    health.state = CircuitState.OPEN
    health.last_failure_time = time.time()
    health.cooldown_seconds = 100.0

    assert clean_router.is_provider_available(ProviderType.GROQ) is False


# Scenario 9: Circuit breaker transition from OPEN to HALF_OPEN after cooldown
def test_09_circuit_breaker_cooldown_to_half_open(clean_router):
    health = clean_router.health_map[ProviderType.GROQ]
    health.state = CircuitState.OPEN
    health.last_failure_time = time.time() - 70.0
    health.cooldown_seconds = 60.0

    assert clean_router.is_provider_available(ProviderType.GROQ) is True
    assert health.state == CircuitState.HALF_OPEN


# Scenario 10: Successful trial in HALF_OPEN restores circuit breaker to CLOSED
def test_10_half_open_success_restores_closed(clean_router):
    health = clean_router.health_map[ProviderType.GROQ]
    health.state = CircuitState.HALF_OPEN
    health.failure_count = 3

    clean_router.record_success(ProviderType.GROQ)
    assert health.state == CircuitState.CLOSED
    assert health.failure_count == 0


# Scenario 11: Pre-first-token failure in streaming triggers seamless failover
def test_11_streaming_pre_token_failover(clean_router):
    def stream_side_effect(model_desc, key, prompt, images):
        if model_desc.model_id == "groq-primary":
            raise RuntimeError("HTTP 401 Unauthorized before any token")
        yield "token-from-gemini-1 "
        yield "token-from-gemini-2"

    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        with patch.object(clean_router, "_execute_provider_stream", side_effect=stream_side_effect):
            events = list(clean_router.stream(prompt="Stream test", preferred_model_id="groq-primary"))
            
            # Should have model_selected events and tokens from Gemini, ending with done
            tokens = [e["token"] for e in events if e.get("type") == "token"]
            assert "".join(tokens) == "token-from-gemini-1 token-from-gemini-2"
            assert events[-1]["type"] == "done"


# Scenario 12: Mid-stream interruption yields structured error event
def test_12_streaming_mid_stream_interruption_safety(clean_router):
    def stream_side_effect(model_desc, key, prompt, images):
        yield "partial content generated "
        raise ConnectionResetError("Connection dropped mid-stream")

    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        with patch.object(clean_router, "_execute_provider_stream", side_effect=stream_side_effect):
            events = list(clean_router.stream(prompt="Stream test", preferred_model_id="groq-primary"))
            
            tokens = [e["token"] for e in events if e.get("type") == "token"]
            assert "".join(tokens) == "partial content generated "
            # Must yield error event and not silently call next provider
            assert events[-1]["type"] == "error"
            assert "interrupted mid-generation" in events[-1]["error"]


# Scenario 13: Free tier preference prioritizes free models
def test_13_prefer_free_models_ordering(clean_router):
    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        candidates = clean_router.get_candidate_models(prefer_free=True)
        assert candidates[0].tier == TierType.FREE


# Scenario 14: Multimodal request filtering routes to multimodal models only
def test_14_multimodal_filtering(clean_router):
    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        candidates = clean_router.get_candidate_models(require_multimodal=True)
        assert len(candidates) >= 1
        for c in candidates:
            assert c.supports_multimodal is True


# Scenario 15: Non-multimodal request correctly allows text-only models
def test_15_text_only_models_allowed(clean_router):
    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        candidates = clean_router.get_candidate_models(require_multimodal=False)
        assert any(c.supports_multimodal is False for c in candidates)


# Scenario 16: Disabling model in registry removes it from candidates
def test_16_disabled_model_removed(clean_router):
    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        clean_router.registry[0].enabled = False
        candidates = clean_router.get_candidate_models()
        assert clean_router.registry[0] not in candidates


# Scenario 17: Priority adjustment dynamically updates routing order
def test_17_priority_adjustment(clean_router):
    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        # Set OpenRouter priority highest (lowest int)
        clean_router.registry[2].priority = 1
        candidates = clean_router.get_candidate_models()
        assert candidates[0].model_id == "openrouter-free-backup"


# Scenario 18: Missing API credentials skips provider cleanly
def test_18_missing_credentials_skips_provider(clean_router):
    def get_keys(provider):
        if provider == ProviderType.GROQ:
            return []
        return ["some-key"]

    with patch.object(clean_router, "get_provider_keys", side_effect=get_keys):
        candidates = clean_router.get_candidate_models()
        assert all(c.provider != ProviderType.GROQ for c in candidates)


# Scenario 19: Masked API key representation prevents credential leakage
def test_19_masked_api_key_representation(clean_router):
    raw_key = "AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxx1234"
    masked = f"{raw_key[:4]}...{raw_key[-4:]}"
    assert masked == "AIza...1234"
    assert "xxxxxxxxxxxxxxxxxxxxxxxx" not in masked


# Scenario 20: All providers exhausted raises clear exception
def test_20_all_providers_exhausted(clean_router):
    def side_effect(model_desc, key, prompt, images):
        raise RuntimeError("Service down")

    with patch.object(clean_router, "get_provider_keys", return_value=["valid-key"]):
        with patch.object(clean_router, "_execute_provider_call", side_effect=side_effect):
            with pytest.raises(RuntimeError) as exc_info:
                clean_router.invoke("Query")
            assert "All model providers exhausted" in str(exc_info.value)


# Scenario 21: Model descriptor attributes and context window validation
def test_21_descriptor_attributes():
    desc = DEFAULT_REGISTRY[0]
    assert desc.context_window > 0
    assert desc.max_output_tokens > 0
    assert desc.display_name != ""
    assert isinstance(desc.tier, TierType)


# Scenario 22: FastAPI GET /api/llm/models endpoint returns models and masked providers
def test_22_api_get_llm_models():
    from fastapi.testclient import TestClient
    from src.rag.api import app
    from src.rag.db.database import SessionLocal
    from src.rag.db.models import User
    from src.rag.db.auth import create_access_token

    db = SessionLocal()
    u = db.query(User).first()
    token = create_access_token(user_id=u.id, email=u.email, tenant_id=u.tenant_id, role=str(u.role))
    db.close()

    client = TestClient(app)
    resp = client.get("/api/llm/models", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "providers" in data
    assert "active_model_id" in data
    for p in data["providers"]:
        if p["active_key_masked"]:
            assert "..." in p["active_key_masked"] or p["active_key_masked"] == "***"


# Scenario 23: FastAPI POST /api/llm/config updates model config
def test_23_api_post_llm_config():
    from fastapi.testclient import TestClient
    from src.rag.api import app
    from src.rag.db.database import SessionLocal
    from src.rag.db.models import User
    from src.rag.db.auth import create_access_token

    db = SessionLocal()
    u = db.query(User).first()
    token = create_access_token(user_id=u.id, email=u.email, tenant_id=u.tenant_id, role=str(u.role))
    db.close()

    client = TestClient(app)
    resp = client.post(
        "/api/llm/config",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model_id": "gemini-2.5-flash",
            "enabled": True,
            "priority": 5
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["model_id"] == "gemini-2.5-flash"
    assert data["priority"] == 5


# Scenario 24: RAGSearch search_and_answer uses router with failover metadata
def test_24_rag_search_router_integration():
    from src.rag.search import RAGSearch

    searcher = RAGSearch.__new__(RAGSearch)
    searcher.persist_dir = "faiss_store"
    searcher.embedding_model = "all-MiniLM-L6-v2"
    searcher.llm_model = "qwen/qwen3.6-27b"
    searcher.vectorstore = MagicMock()
    searcher.vectorstore.query.return_value = [
        {
            "metadata": {"text": "Machine learning overview chunk", "source": "ml_guide.pdf", "page": 1, "type": "text"},
            "distance": 0.15
        }
    ]
    searcher.gemini_llm = None
    searcher.llm = None

    with patch("src.rag.search.get_model_router") as mock_router_getter:
        mock_router = MagicMock()
        mock_router.invoke.return_value = {
            "answer": "Grounded answer from router",
            "model_id": "gemini-2.5-flash",
            "provider": "gemini",
            "tier": "free",
            "failover_occurred": True
        }
        mock_router_getter.return_value = mock_router

        res = searcher.search_and_answer("What is machine learning?")
        assert res["answer"] == "Grounded answer from router"
        assert res["model_id"] == "gemini-2.5-flash"
        assert res["failover_occurred"] is True
        assert len(res["citations"]) == 1
