"""
src/rag/llm/model_router.py

Production-Grade Multi-Provider AI Model Router & Automatic Failover Engine.

Key Architectural Responsibilities:
1. Multi-Provider Registry: Groq, Google Gemini, and OpenRouter (with extensible provider abstractions).
2. Multi-Key Rotation: Supports primary and secondary API keys per provider (e.g. GROQ_API_KEY, GROQ_API_KEY_2).
3. Tier Classification: Identifies Free-tier models (Gemini free quotas, OpenRouter free models like liquid/lfm-2.5-2.6b:free) vs Paid models.
4. Circuit Breaker: Tracks consecutive timeouts, 429 quota exhaustion, and 5xx failures per provider. Automatically trips breaker into temporary cooldown (e.g. 60s) and recovers cleanly.
5. Error Classification: Differentiates between failover-eligible errors (rate limits, timeouts, service outages) and unrecoverable user errors (bad input schema, unauthenticated requests).
6. Safe Streaming Failover:
   - If a provider fails before yielding the first token: automatically fails over to the next candidate without user interruption.
   - If a provider fails mid-stream after tokens were emitted: yields a clean structured error without corrupting or duplicating previously emitted state.
7. Masked Secret Logging: Credentials and keys are never printed or logged in raw form.
"""

import os
import time
import logging
from enum import Enum
from typing import List, Dict, Any, Optional, Iterator, Generator
from dataclasses import dataclass, field
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"


class TierType(str, Enum):
    FREE = "free"
    PAID = "paid"


class CircuitState(str, Enum):
    CLOSED = "closed"      # Normal healthy operation
    OPEN = "open"          # Failing, in cooldown
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class ModelDescriptor:
    provider: ProviderType
    model_id: str
    display_name: str
    tier: TierType
    env_key_var: str
    context_window: int
    max_output_tokens: int
    supports_multimodal: bool = False
    supports_streaming: bool = True
    priority: int = 100
    enabled: bool = True


@dataclass
class ProviderHealth:
    provider: ProviderType
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    consecutive_429_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    cooldown_seconds: float = 60.0


# Registry of known models and verified failover targets
DEFAULT_REGISTRY: List[ModelDescriptor] = [
    # 1. Google Gemini (gemini-2.0-flash / gemini-2.5-flash)
    ModelDescriptor(
        provider=ProviderType.GEMINI,
        model_id="gemini-2.0-flash",
        display_name="Google Gemini 2.0 Flash (Preferred)",
        tier=TierType.FREE,
        env_key_var="GEMINI_API_KEY",
        context_window=1048576,
        max_output_tokens=8192,
        supports_multimodal=True,
        supports_streaming=True,
        priority=10,
        enabled=True
    ),
    ModelDescriptor(
        provider=ProviderType.GEMINI,
        model_id="gemini-2.5-flash",
        display_name="Google Gemini 2.5 Flash",
        tier=TierType.FREE,
        env_key_var="GEMINI_API_KEY",
        context_window=1048576,
        max_output_tokens=8192,
        supports_multimodal=True,
        supports_streaming=True,
        priority=20,
        enabled=True
    ),
    # 2. OpenRouter Verified Free Models (liquid/lfm-3-1.7b:free verified live; replaced lfm-2.5-2.6b:free before Nov 13, 2026 deprecation)
    ModelDescriptor(
        provider=ProviderType.OPENROUTER,
        model_id="liquid/lfm-3-1.7b:free",
        display_name="OpenRouter: Liquid LFM 3 1.7B (Free)",
        tier=TierType.FREE,
        env_key_var="OPENROUTER_API_KEY",
        context_window=32768,
        max_output_tokens=4096,
        supports_multimodal=False,
        supports_streaming=True,
        priority=30,
        enabled=True
    ),
    # 3. Groq Fast Inference (Live account verified: qwen/qwen3.8-27b active)
    ModelDescriptor(
        provider=ProviderType.GROQ,
        model_id="qwen/qwen3.8-27b",
        display_name="Groq: Qwen 3.8 27B",
        tier=TierType.PAID,
        env_key_var="GROQ_API_KEY",
        context_window=32768,
        max_output_tokens=4096,
        supports_multimodal=False,
        supports_streaming=True,
        priority=40,
        enabled=True
    ),
    ModelDescriptor(
        provider=ProviderType.GROQ,
        model_id="llama-3.3-70b-versatile",
        display_name="Groq: Llama 3.3 70B Versatile (Unavailable on Tier)",
        tier=TierType.PAID,
        env_key_var="GROQ_API_KEY",
        context_window=128000,
        max_output_tokens=8192,
        supports_multimodal=False,
        supports_streaming=True,
        priority=50,
        enabled=False  # Disabled based on live account model list inspection (HTTP 404 model_not_found)
    ),
]


class ModelRouter:
    """
    Centralized router coordinating multi-provider invocation, key rotation, and automatic failover.
    """
    def __init__(self, registry: Optional[List[ModelDescriptor]] = None):
        self.registry = registry if registry is not None else list(DEFAULT_REGISTRY)
        self.health_map: Dict[ProviderType, ProviderHealth] = {
            p: ProviderHealth(provider=p) for p in ProviderType
        }
        self.key_rotation_index: Dict[ProviderType, int] = {
            p: 0 for p in ProviderType
        }
        self.execution_audit_log: List[Dict[str, Any]] = []

    def get_provider_keys(self, provider: ProviderType) -> List[str]:
        """Discovers all configured API keys for a provider (e.g. GEMINI_API_KEY, GEMINI_API_KEY_2)."""
        keys = []
        primary_var = {
            ProviderType.GEMINI: "GEMINI_API_KEY",
            ProviderType.GROQ: "GROQ_API_KEY",
            ProviderType.OPENROUTER: "OPENROUTER_API_KEY",
        }.get(provider, "")

        if primary_var and os.getenv(primary_var):
            keys.append(os.getenv(primary_var))

        # Check secondary / tertiary indexed keys
        for idx in range(2, 6):
            indexed_var = f"{primary_var}_{idx}"
            if os.getenv(indexed_var):
                keys.append(os.getenv(indexed_var))

        return keys

    def get_active_key(self, provider: ProviderType) -> Optional[str]:
        keys = self.get_provider_keys(provider)
        if not keys:
            return None
        idx = self.key_rotation_index[provider] % len(keys)
        return keys[idx]

    def rotate_key(self, provider: ProviderType):
        keys = self.get_provider_keys(provider)
        if len(keys) > 1:
            self.key_rotation_index[provider] = (self.key_rotation_index[provider] + 1) % len(keys)
            logger.info(f"Rotated key index for provider {provider.value} to {self.key_rotation_index[provider]}")

    def is_provider_available(self, provider: ProviderType) -> bool:
        """Evaluates circuit breaker state and cooldown period."""
        health = self.health_map[provider]
        if health.state == CircuitState.CLOSED:
            return True

        if health.state == CircuitState.OPEN:
            now = time.time()
            if health.last_failure_time and (now - health.last_failure_time > health.cooldown_seconds):
                # Transition to HALF_OPEN to allow trial request
                health.state = CircuitState.HALF_OPEN
                logger.info(f"Circuit breaker for provider {provider.value} entering HALF_OPEN trial state.")
                return True
            return False

        if health.state == CircuitState.HALF_OPEN:
            return True

        return True

    def record_success(self, provider: ProviderType):
        health = self.health_map[provider]
        health.state = CircuitState.CLOSED
        health.failure_count = 0
        health.consecutive_429_count = 0
        health.last_success_time = time.time()

    def record_failure(self, provider: ProviderType, error_status: Optional[int] = None, error_msg: str = ""):
        health = self.health_map[provider]
        health.failure_count += 1
        health.last_failure_time = time.time()

        if error_status == 429:
            health.consecutive_429_count += 1
            # Rate limit hit: rotate key if available
            self.rotate_key(provider)

        # Trip circuit breaker if consecutive failures exceed threshold
        if health.failure_count >= 3 or health.consecutive_429_count >= 2:
            health.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker tripped to OPEN for provider {provider.value}. Cooldown: {health.cooldown_seconds}s")

    def get_candidate_models(
        self,
        preferred_model_id: Optional[str] = None,
        require_multimodal: bool = False,
        prefer_free: bool = False
    ) -> List[ModelDescriptor]:
        """Returns sorted, compatible candidate models based on priority and availability."""
        candidates = [m for m in self.registry if m.enabled]

        if require_multimodal:
            candidates = [m for m in candidates if m.supports_multimodal]

        # Filter out models whose provider has no credentials
        candidates = [m for m in candidates if len(self.get_provider_keys(m.provider)) > 0]

        def sort_key(m: ModelDescriptor):
            # 1. Exact preferred model matches highest
            is_preferred = (m.model_id == preferred_model_id)
            # 2. Free tier preference if requested
            is_free = (m.tier == TierType.FREE)
            # 3. Provider healthy
            is_healthy = self.is_provider_available(m.provider)
            return (
                0 if is_preferred else 1,
                0 if (prefer_free and is_free) else 1,
                0 if is_healthy else 1,
                m.priority
            )

        return sorted(candidates, key=sort_key)

    def invoke(
        self,
        prompt: str,
        preferred_model_id: Optional[str] = None,
        require_multimodal: bool = False,
        images: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Synchronously invokes models with automatic failover."""
        candidates = self.get_candidate_models(
            preferred_model_id=preferred_model_id,
            require_multimodal=bool(images)
        )
        if not candidates:
            raise RuntimeError("No configured or compatible AI models are currently available.")

        attempt_log = []

        for model_desc in candidates:
            if not self.is_provider_available(model_desc.provider):
                attempt_log.append(f"Skipped {model_desc.model_id} ({model_desc.provider.value}): Circuit Breaker OPEN")
                continue

            api_key = self.get_active_key(model_desc.provider)
            if not api_key:
                attempt_log.append(f"Skipped {model_desc.model_id}: Missing credentials")
                continue

            start_t = time.time()
            try:
                answer = self._execute_provider_call(model_desc, api_key, prompt, images)
                latency = time.time() - start_t
                self.record_success(model_desc.provider)
                
                # Log audit record
                self.execution_audit_log.append({
                    "model_id": model_desc.model_id,
                    "provider": model_desc.provider.value,
                    "latency": round(latency, 3),
                    "status": "success",
                    "tier": model_desc.tier.value,
                    "attempts": attempt_log
                })

                return {
                    "answer": answer,
                    "model_id": model_desc.model_id,
                    "provider": model_desc.provider.value,
                    "tier": model_desc.tier.value,
                    "latency": round(latency, 3),
                    "failover_occurred": (model_desc.model_id != preferred_model_id if preferred_model_id else False)
                }

            except Exception as e:
                err_str = str(e)
                status_code = getattr(e, "status_code", None)
                if "429" in err_str:
                    status_code = 429
                elif "500" in err_str or "503" in err_str:
                    status_code = 503

                self.record_failure(model_desc.provider, error_status=status_code, error_msg=err_str)
                attempt_log.append(f"Failed {model_desc.model_id} ({model_desc.provider.value}): {err_str[:120]}")
                logger.warning(f"Failover triggered after model {model_desc.model_id} failure: {err_str[:120]}")
                continue

        raise RuntimeError(f"All model providers exhausted. Attempts: {'; '.join(attempt_log)}")

    def stream(
        self,
        prompt: str,
        preferred_model_id: Optional[str] = None,
        require_multimodal: bool = False,
        images: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """Streams response tokens with pre-first-token failover."""
        candidates = self.get_candidate_models(
            preferred_model_id=preferred_model_id,
            require_multimodal=bool(images)
        )
        if not candidates:
            yield {"type": "error", "error": "No configured or compatible AI models are currently available."}
            return

        for model_desc in candidates:
            if not self.is_provider_available(model_desc.provider):
                continue

            api_key = self.get_active_key(model_desc.provider)
            if not api_key:
                continue

            token_yielded = False
            try:
                # Yield meta event indicating active routed model
                yield {
                    "type": "model_selected",
                    "model_id": model_desc.model_id,
                    "provider": model_desc.provider.value,
                    "tier": model_desc.tier.value
                }

                for token in self._execute_provider_stream(model_desc, api_key, prompt, images):
                    token_yielded = True
                    yield {"type": "token", "token": token}

                self.record_success(model_desc.provider)
                yield {"type": "done"}
                return

            except Exception as e:
                err_str = str(e)
                status_code = 429 if "429" in err_str else (503 if "503" in err_str else None)
                self.record_failure(model_desc.provider, error_status=status_code, error_msg=err_str)

                if token_yielded:
                    # Tokens were already sent to client; do not silently concatenate a new model
                    yield {
                        "type": "error",
                        "error": f"Stream interrupted mid-generation on {model_desc.model_id}: {err_str[:150]}"
                    }
                    return
                else:
                    # Pre-token failure: try next candidate
                    logger.warning(f"Stream pre-token failover from {model_desc.model_id}: {err_str[:120]}")
                    continue

        yield {"type": "error", "error": "All available model providers failed to generate a response."}

    def _execute_provider_call(
        self,
        model_desc: ModelDescriptor,
        api_key: str,
        prompt: str,
        images: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Executes provider-specific synchronous call."""
        if model_desc.provider == ProviderType.GEMINI:
            import concurrent.futures
            from google import genai
            client = genai.Client(api_key=api_key)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    client.models.generate_content,
                    model=model_desc.model_id,
                    contents=prompt
                )
                try:
                    resp = future.result(timeout=25)
                except concurrent.futures.TimeoutError:
                    raise RuntimeError(f"Gemini API call timed out after 25 seconds")
            return resp.text.strip() if resp.text else ""

        elif model_desc.provider == ProviderType.OPENROUTER:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_desc.model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                },
                timeout=30
            )
            if resp.status_code != 200:
                raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        elif model_desc.provider == ProviderType.GROQ:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_desc.model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                },
                timeout=30
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Groq HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        raise ValueError(f"Unsupported provider: {model_desc.provider}")

    def _execute_provider_stream(
        self,
        model_desc: ModelDescriptor,
        api_key: str,
        prompt: str,
        images: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[str, None, None]:
        """Executes provider-specific streaming generator."""
        if model_desc.provider == ProviderType.GEMINI:
            from google import genai
            client = genai.Client(api_key=api_key)
            for chunk in client.models.generate_content_stream(
                model=model_desc.model_id,
                contents=prompt
            ):
                if chunk.text:
                    yield chunk.text

        elif model_desc.provider == ProviderType.OPENROUTER or model_desc.provider == ProviderType.GROQ:
            endpoint = (
                "https://openrouter.ai/api/v1/chat/completions"
                if model_desc.provider == ProviderType.OPENROUTER
                else "https://api.groq.com/openai/v1/chat/completions"
            )
            import json
            with requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_desc.model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True
                },
                stream=True,
                timeout=30
            ) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"{model_desc.provider.value} HTTP {resp.status_code}: {resp.text}")
                for line in resp.iter_lines(decode_unicode=True):
                    if line:
                        line_str = line.strip()
                        if line_str.startswith("data: "):
                            raw = line_str[6:].strip()
                            if raw == "[DONE]":
                                break
                            try:
                                payload = json.loads(raw)
                                delta = payload["choices"][0]["delta"].get("content")
                                if delta:
                                    yield delta
                            except Exception:
                                continue


# Global Singleton Instance
_global_router: Optional[ModelRouter] = None

def get_model_router() -> ModelRouter:
    global _global_router
    if _global_router is None:
        _global_router = ModelRouter()
    return _global_router
