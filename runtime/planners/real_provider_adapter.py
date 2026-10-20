"""Real LLM Provider Adapter and Controlled Inference Transport (RT-07B0 / RT-07B0A).

Provides trusted HTTP transport abstraction connecting LLMPlanner and HybridPlanner
to real external model endpoints (OpenAI-compatible and Anthropic APIs) under strict
Fog-of-War and laboratory isolation:

1. Strictly adheres to CONTROLLED_INFERENCE_CONFIG_V1:
   - temperature = 0.0 (greedy decoding)
   - top_p = 1.0
   - max_output_tokens = 512
   - timeout_seconds = 30.0
   - max_retries = 2
   - backoff_factor = 1.5
2. User-Configurable Provider and Model (RT-07B0A):
   - Reuses existing repository configuration interfaces (ProfileStore / DASHBOARD_MODEL_PROFILE / .env)
   - Supports user-specified provider_type, model_id, and base_url
   - Zero hardcoded model names, token costs, or context limits
   - Discloses provider_seed_supported = False
3. Multi-layer Budget and Circuit Breaker (RT-07B0A):
   - Tracks all 7 accounting metrics:
     planner_decisions, logical_provider_calls, HTTP_attempts, retry_attempts,
     input_tokens, output_tokens, consecutive_errors, cumulative_errors
   - Capped HTTP attempts (max 12,000) halts retry amplification
   - Consecutive error breaker (trips at 5) and cumulative error breaker (trips at 20)
   - Preserves completed episode records on circuit-breaker trip
4. Zero credentials in Git, logs, traces, or benchmark results:
   - API keys loaded from ProfileStore or environment variables
   - Automatically redacts API keys from all errors, logs, and telemetry
"""
from __future__ import annotations

import dataclasses
import http.client
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping, Sequence
import urllib.parse

from runtime.evaluation.usage_costs import MeteredReviewResponse, TokenUsage, UsageExtractor
from runtime.evidence.discovery_recorder import redact_secrets

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Frozen inference parameters from protocol_freeze.json (CONTROLLED_INFERENCE_CONFIG_V1)
FROZEN_INFERENCE_CONFIG_VERSION = "CONTROLLED_INFERENCE_CONFIG_V1"
FROZEN_TEMPERATURE = 0.0
FROZEN_TOP_P = 1.0
FROZEN_MAX_OUTPUT_TOKENS = 512
FROZEN_TIMEOUT_SECONDS = 30.0
FROZEN_MAX_RETRIES = 2
FROZEN_BACKOFF_FACTOR = 1.5


class RealProviderError(Exception):
    """Base exception for real LLM provider errors."""

    def __init__(self, message: str, error_code: str = "PROVIDER_ERROR", status_code: int | None = None) -> None:
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(redact_secrets(message))


class RealProviderNotConfiguredError(RealProviderError):
    """Raised when real LLM provider credentials or model configuration is missing."""

    def __init__(self, message: str = "REAL_LLM_BENCHMARK_BLOCKED: Missing provider credentials or model configuration") -> None:
        super().__init__(message=message, error_code="REAL_LLM_BENCHMARK_BLOCKED")


class RealProviderTimeoutError(RealProviderError, TimeoutError):
    """Raised when provider request exceeds bounded timeout."""

    def __init__(self, message: str = "PROVIDER_TIMEOUT: Request timed out") -> None:
        super().__init__(message=message, error_code="PROVIDER_TIMEOUT")


class RealProviderIncompatibleConfigError(RealProviderError):
    """Raised when configuration violates CONTROLLED_INFERENCE_CONFIG_V1."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, error_code="MODEL_CONFIG_INCOMPATIBLE")


class CircuitBreakerTrippedError(RealProviderError):
    """Raised when safety budget, rate limit, or consecutive error threshold is exceeded."""

    def __init__(self, message: str, error_code: str = "CIRCUIT_BREAKER_TRIPPED") -> None:
        super().__init__(message=message, error_code=error_code)


class TokenBudgetEnforcementUnavailableError(CircuitBreakerTrippedError):
    """Raised when an endpoint cannot reliably guarantee strict total-token ceilings pre-dispatch."""

    def __init__(
        self,
        message: str = "SMOKE_TOKEN_BUDGET_ENFORCEMENT_UNAVAILABLE: Endpoint cannot guarantee strict total-token cap",
    ) -> None:
        super().__init__(message=message, error_code="SMOKE_TOKEN_BUDGET_ENFORCEMENT_UNAVAILABLE")


@dataclasses.dataclass
class BudgetAccountingMetrics:
    """Comprehensive token and execution accounting metrics (RT-07B0 / RT-07B0A / RT-07-SMOKE-AUDIT)."""

    planner_decisions: int = 0
    logical_provider_calls: int = 0
    http_attempts: int = 0
    retry_attempts: int = 0
    estimated_input_tokens: int = 0
    authoritative_input_tokens: int | None = None
    reserved_output_tokens: int = FROZEN_MAX_OUTPUT_TOKENS
    provider_reported_input_tokens: int = 0
    provider_reported_output_tokens: int = 0
    provider_reported_total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    consecutive_errors: int = 0
    cumulative_errors: int = 0
    authorization_incidents: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ProviderBudgetLimits:
    """Execution ceilings to prevent spend bypass and runaway execution."""

    max_decisions: int = 10_000
    max_logical_calls: int = 6_000
    max_http_attempts: int = 12_000  # Halts retry amplification (e.g. 6k calls * 2 retries)
    max_retry_attempts: int = 6_000
    max_input_tokens: int = 10_000_000
    max_output_tokens: int = 2_000_000
    max_consecutive_errors: int = 5
    max_cumulative_errors: int = 20
    max_requests_per_minute: int = 60
    # Strict token authorization ceiling (e.g. 1,000 global tokens for live smoke testing)
    strict_total_token_cap: int | None = None
    require_authoritative_input_bound: bool = False


class ProviderBudgetGuard:
    """Monitors real provider execution, enforces spending limits and trips circuit breaker."""

    def __init__(self, limits: ProviderBudgetLimits | None = None) -> None:
        self.limits = limits or ProviderBudgetLimits()
        self.metrics = BudgetAccountingMetrics()
        self.monetary_cap_status: str = "MONETARY_CAP_NOT_ENFORCED"
        self._request_timestamps: list[float] = []
        self._tripped = False
        self._trip_reason = ""

    @property
    def is_healthy(self) -> bool:
        return not self._tripped

    @property
    def trip_reason(self) -> str:
        return self._trip_reason

    def get_spend_accounting_summary(self) -> dict[str, Any]:
        """Return full spend accounting summary with explicit monetary cap status."""
        return {
            "planner_decisions": self.metrics.planner_decisions,
            "logical_provider_calls": self.metrics.logical_provider_calls,
            "http_attempts": self.metrics.http_attempts,
            "retry_attempts": self.metrics.retry_attempts,
            "estimated_input_tokens": self.metrics.estimated_input_tokens,
            "authoritative_input_tokens": self.metrics.authoritative_input_tokens,
            "reserved_output_tokens": self.metrics.reserved_output_tokens,
            "provider_reported_input_tokens": self.metrics.provider_reported_input_tokens,
            "provider_reported_output_tokens": self.metrics.provider_reported_output_tokens,
            "provider_reported_total_tokens": self.metrics.provider_reported_total_tokens,
            "input_tokens": self.metrics.input_tokens,
            "output_tokens": self.metrics.output_tokens,
            "reasoning_tokens": self.metrics.reasoning_tokens,
            "consecutive_errors": self.metrics.consecutive_errors,
            "cumulative_errors": self.metrics.cumulative_errors,
            "authorization_incidents": list(self.metrics.authorization_incidents),
            "monetary_cap_status": self.monetary_cap_status,
            "estimated_monetary_spend_usd": None,
            "monetary_accounting_note": (
                "User-configured models have arbitrary external or local pricing; "
                "monetary spending is governed by strict token and HTTP attempt ceilings "
                "rather than unverified currency estimates."
            ),
        }

    def evaluate_pre_dispatch(
        self,
        estimated_input_tokens: int,
        reserved_output_tokens: int = FROZEN_MAX_OUTPUT_TOKENS,
        authoritative_input_tokens: int | None = None,
    ) -> tuple[bool, str]:
        """Evaluate prospective token spend against strict authorization limits before dispatch."""
        if self._tripped:
            raise CircuitBreakerTrippedError(f"Circuit breaker already tripped: {self._trip_reason}")

        self.metrics.estimated_input_tokens += max(0, estimated_input_tokens)
        self.metrics.authoritative_input_tokens = authoritative_input_tokens
        self.metrics.reserved_output_tokens = reserved_output_tokens

        if self.limits.strict_total_token_cap is not None:
            # Check authoritative bounding requirement (fail-closed if endpoint cannot bound inputs)
            if self.limits.require_authoritative_input_bound and authoritative_input_tokens is None:
                self._trip(
                    "SMOKE_TOKEN_BUDGET_ENFORCEMENT_UNAVAILABLE: Configured endpoint does not supply "
                    "an authoritative pre-dispatch input token bound or provably conservative total-token bound. "
                    "Live dispatch under strict total-token ceiling cannot be guaranteed.",
                    error_class=TokenBudgetEnforcementUnavailableError,
                )

            effective_input = authoritative_input_tokens if authoritative_input_tokens is not None else estimated_input_tokens
            reservation = effective_input + reserved_output_tokens
            current_spent = self.metrics.provider_reported_total_tokens
            if current_spent + reservation > self.limits.strict_total_token_cap:
                remaining = max(0, self.limits.strict_total_token_cap - current_spent)
                self._trip(
                    f"SMOKE_TOKEN_BUDGET_EXCEEDED: Prospective reservation {reservation} tokens "
                    f"(effective_input={effective_input}, output_reservation={reserved_output_tokens}) exceeds remaining "
                    f"authorized budget of {remaining} tokens (strict_cap={self.limits.strict_total_token_cap}, "
                    f"current_spent={current_spent})."
                )

        return True, "PRE_DISPATCH_RESERVATION_GRANTED"

    def record_decision(self) -> None:
        """Track high-level planner decision count."""
        self.metrics.planner_decisions += 1
        if self.metrics.planner_decisions > self.limits.max_decisions:
            self._trip(f"MAX_DECISIONS_EXCEEDED: Exceeded ceiling of {self.limits.max_decisions} decisions")

    def record_logical_call(self) -> None:
        """Record entry to a logical LLM completion request."""
        if self._tripped:
            raise CircuitBreakerTrippedError(f"Circuit breaker already tripped: {self._trip_reason}")

        self.metrics.logical_provider_calls += 1
        if self.metrics.logical_provider_calls > self.limits.max_logical_calls:
            self._trip(f"MAX_LOGICAL_CALLS_EXCEEDED: Exceeded ceiling of {self.limits.max_logical_calls} calls")

    def record_http_attempt(self) -> None:
        """Record each HTTP attempt (initial and retries) to cap spend and halt retry amplification."""
        if self._tripped:
            raise CircuitBreakerTrippedError(f"Circuit breaker already tripped: {self._trip_reason}")

        # Check rate limit per minute
        now = time.monotonic()
        self._request_timestamps.append(now)
        # Prune older than 60s
        self._request_timestamps = [t for t in self._request_timestamps if now - t <= 60.0]
        if len(self._request_timestamps) > self.limits.max_requests_per_minute:
            self._trip(
                f"RATE_LIMIT_EXCEEDED: Rate ceiling of {self.limits.max_requests_per_minute} req/min exceeded"
            )

        self.metrics.http_attempts += 1
        if self.metrics.http_attempts > self.limits.max_http_attempts:
            self._trip(
                f"MAX_HTTP_ATTEMPTS_EXCEEDED: Ceiled at {self.limits.max_http_attempts} HTTP attempts; "
                "halted retry amplification"
            )

    def record_retry(
        self,
        estimated_input_tokens: int = 0,
        reserved_output_tokens: int = FROZEN_MAX_OUTPUT_TOKENS,
        authoritative_input_tokens: int | None = None,
    ) -> None:
        """Record a retry attempt, re-evaluating spend against strict total-token ceiling."""
        self.metrics.retry_attempts += 1
        if self.metrics.retry_attempts > self.limits.max_retry_attempts:
            self._trip(f"MAX_RETRY_ATTEMPTS_EXCEEDED: Exceeded ceiling of {self.limits.max_retry_attempts} retries")

        if self.limits.strict_total_token_cap is not None:
            effective_input = authoritative_input_tokens if authoritative_input_tokens is not None else estimated_input_tokens
            reservation = effective_input + reserved_output_tokens
            current_spent = self.metrics.provider_reported_total_tokens
            if current_spent + reservation > self.limits.strict_total_token_cap:
                remaining = max(0, self.limits.strict_total_token_cap - current_spent)
                self._trip(
                    f"RETRY_TOKEN_BUDGET_EXCEEDED: Retry reservation {reservation} exceeds remaining "
                    f"authorized budget of {remaining} tokens (spent={current_spent}, cap={self.limits.strict_total_token_cap})"
                )

    def record_success(
        self,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int | None = None,
        reasoning_tokens: int | None = None,
    ) -> None:
        """Record successful call outcome and update token accounting."""
        self.metrics.consecutive_errors = 0
        self.metrics.input_tokens += max(0, input_tokens)
        self.metrics.output_tokens += max(0, output_tokens)
        self.metrics.provider_reported_input_tokens += max(0, input_tokens)
        self.metrics.provider_reported_output_tokens += max(0, output_tokens)
        if reasoning_tokens:
            self.metrics.reasoning_tokens += max(0, reasoning_tokens)

        reported_total = total_tokens if total_tokens is not None else (input_tokens + output_tokens)
        self.metrics.provider_reported_total_tokens += max(0, reported_total)

        if self.metrics.input_tokens > self.limits.max_input_tokens:
            self._trip(f"MAX_INPUT_TOKENS_EXCEEDED: Input tokens exceeded {self.limits.max_input_tokens}")
        if self.metrics.output_tokens > self.limits.max_output_tokens:
            self._trip(f"MAX_OUTPUT_TOKENS_EXCEEDED: Output tokens exceeded {self.limits.max_output_tokens}")

        # Enforce strict total-token ceiling post-response as well
        if self.limits.strict_total_token_cap is not None:
            if self.metrics.provider_reported_total_tokens > self.limits.strict_total_token_cap:
                incident = {
                    "event": "TOKEN_AUTHORIZATION_BREACH",
                    "strict_cap": self.limits.strict_total_token_cap,
                    "reported_total": self.metrics.provider_reported_total_tokens,
                    "excess": self.metrics.provider_reported_total_tokens - self.limits.strict_total_token_cap,
                    "timestamp": time.time(),
                }
                self.metrics.authorization_incidents.append(incident)
                self._trip(
                    f"TOKEN_AUTHORIZATION_BREACH: Provider reported cumulative usage of "
                    f"{self.metrics.provider_reported_total_tokens} tokens, breaching strict cap of "
                    f"{self.limits.strict_total_token_cap}"
                )

    def record_error(self) -> None:
        """Record a failed HTTP or logical attempt; trips if error thresholds are reached."""
        self.metrics.consecutive_errors += 1
        self.metrics.cumulative_errors += 1

        if self.metrics.consecutive_errors >= self.limits.max_consecutive_errors:
            self._trip(
                f"CONSECUTIVE_ERRORS_EXCEEDED: Circuit breaker tripped after "
                f"{self.metrics.consecutive_errors} consecutive provider errors"
            )

        if self.metrics.cumulative_errors >= self.limits.max_cumulative_errors:
            self._trip(
                f"CUMULATIVE_ERRORS_EXCEEDED: Circuit breaker tripped after "
                f"{self.metrics.cumulative_errors} cumulative provider errors"
            )

    def _trip(
        self,
        reason: str,
        error_class: type[CircuitBreakerTrippedError] = CircuitBreakerTrippedError,
    ) -> None:
        self._tripped = True
        self._trip_reason = reason
        raise error_class(reason)


@dataclasses.dataclass(frozen=True)
class RealLLMProviderConfig:
    """Validated configuration for user-configurable real LLM model inference (RT-07B0A)."""

    provider_type: str = "openai-compatible"  # "openai-compatible" or "anthropic"
    model: str = ""  # User-configured; no hardcoded defaults
    api_base: str = ""  # Base URL endpoint (defaults to official provider URL if empty)
    api_key: str | None = dataclasses.field(default=None, repr=False)
    temperature: float = FROZEN_TEMPERATURE
    top_p: float = FROZEN_TOP_P
    max_output_tokens: int = FROZEN_MAX_OUTPUT_TOKENS
    timeout_seconds: float = FROZEN_TIMEOUT_SECONDS
    max_retries: int = FROZEN_MAX_RETRIES
    backoff_factor: float = FROZEN_BACKOFF_FACTOR
    provider_seed_supported: bool = False
    requested_seed: int | None = None
    service_tier: str = "default"
    region: str = "global"
    configuration_source: str = "EXPLICIT_CONFIG"
    allow_keyless: bool = False
    authoritative_input_tokens: int | None = None

    def __post_init__(self) -> None:
        # Enforce strict compliance with CONTROLLED_INFERENCE_CONFIG_V1
        if abs(self.temperature - FROZEN_TEMPERATURE) > 1e-6:
            raise RealProviderIncompatibleConfigError(
                f"temperature={self.temperature} violates frozen {FROZEN_TEMPERATURE}"
            )
        if abs(self.top_p - FROZEN_TOP_P) > 1e-6:
            raise RealProviderIncompatibleConfigError(
                f"top_p={self.top_p} violates frozen {FROZEN_TOP_P}"
            )
        if self.max_output_tokens != FROZEN_MAX_OUTPUT_TOKENS:
            raise RealProviderIncompatibleConfigError(
                f"max_output_tokens={self.max_output_tokens} violates frozen {FROZEN_MAX_OUTPUT_TOKENS}"
            )
        if self.timeout_seconds != FROZEN_TIMEOUT_SECONDS:
            raise RealProviderIncompatibleConfigError(
                f"timeout_seconds={self.timeout_seconds} violates frozen {FROZEN_TIMEOUT_SECONDS}"
            )
        if self.max_retries != FROZEN_MAX_RETRIES:
            raise RealProviderIncompatibleConfigError(
                f"max_retries={self.max_retries} violates frozen {FROZEN_MAX_RETRIES}"
            )
        if self.provider_type not in ("openai-compatible", "anthropic"):
            raise RealProviderIncompatibleConfigError(
                f"Unsupported provider_type: {self.provider_type}"
            )

        # Set default base URL if not explicitly given
        if not self.api_base:
            resolved_base = (
                "https://api.anthropic.com/v1"
                if self.provider_type == "anthropic"
                else "https://api.openai.com/v1"
            )
            object.__setattr__(self, "api_base", resolved_base)

    @property
    def is_local_endpoint(self) -> bool:
        """True if api_base points to a genuine loopback endpoint (localhost, 127.0.0.0/8, ::1).

        Wildcard bind addresses such as 0.0.0.0, Docker service names, and external hostnames
        are strictly excluded from automatic loopback trust.
        """
        try:
            parsed = urllib.parse.urlsplit(self.api_base)
            host = (parsed.hostname or "").strip().lower()
            if not host:
                return False
            if host.startswith("[") and host.endswith("]"):
                host = host[1:-1]
            if host == "localhost" or host.endswith(".localhost"):
                return True
            if host == "0.0.0.0":
                return False
            ip = ipaddress.ip_address(host)
            return ip.is_loopback
        except Exception:
            return False

    @property
    def requires_api_key(self) -> bool:
        """Returns True if this endpoint configuration requires an API key.

        1. Genuine loopback endpoints (localhost, 127.0.0.1, ::1) do not require an API key.
        2. Non-loopback endpoints (Docker hostnames, LAN, remote URLs, 0.0.0.0) require an API key
           by default, unless explicit keyless policy (allow_keyless=True) is declared.
        """
        if self.is_local_endpoint:
            return False
        if self.allow_keyless:
            return False
        return True

    @property
    def is_configured(self) -> bool:
        """True if model is configured and credentials are present when required."""
        if not self.model:
            return False
        if self.requires_api_key and not self.api_key:
            return False
        return True

    def to_provenance_record(self) -> dict[str, Any]:
        """Construct immutable configuration provenance record with sensitive credentials redacted."""
        return {
            "provider_type": self.provider_type,
            "model_id": self.model,
            "base_url": self.api_base,
            "adapter_protocol_version": "RT-07B0A_UNIFIED_ADAPTER_V1",
            "inference_parameters": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_output_tokens": self.max_output_tokens,
                "timeout_seconds": self.timeout_seconds,
                "max_retries": self.max_retries,
                "backoff_factor": self.backoff_factor,
            },
            "provider_seed_supported": self.provider_seed_supported,
            "requested_seed": self.requested_seed,
            "api_key_redacted": "[REDACTED]" if self.api_key else None,
            "configuration_source": self.configuration_source,
            "is_local_endpoint": self.is_local_endpoint,
            "requires_api_key": self.requires_api_key,
            "allow_keyless": self.allow_keyless,
            "authoritative_input_tokens": self.authoritative_input_tokens,
            "is_configured": self.is_configured,
            "model_metadata": {
                "context_window": None,
                "parameter_count": None,
                "weights_hash": None,
            },
        }

    @classmethod
    def from_profile_or_env(
        cls,
        provider_type: str | None = None,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        requested_seed: int | None = None,
        allow_keyless: bool | None = None,
        env_file_path: Path | None = None,
    ) -> RealLLMProviderConfig:
        """Resolve model configuration reusing existing ProfileStore mechanism or environment variables.

        Order of precedence:
        1. Explicit caller arguments (e.g. from CLI flags --provider-type, --model-id, --base-url)
        2. Repository ProfileStore (.env DASHBOARD_MODEL_PROFILE)
        3. Standard environment variables (LLM_PROVIDER, LLM_MODEL, LLM_API_BASE, LLM_API_KEY)
        """
        config_source = "DEFAULT"
        if model is not None or provider_type is not None or api_base is not None or api_key is not None:
            config_source = "CLI_OVERRIDE"

        resolved_type = provider_type
        resolved_model = model
        resolved_base = api_base
        resolved_key = api_key
        resolved_allow_keyless = allow_keyless

        # 1. Attempt to load from existing ProfileStore in .env
        env_path = env_file_path or (REPO_ROOT / ".env")
        if env_path.is_file():
            try:
                from dashboards.app.backend.model_profiles import ProfileStore

                store = ProfileStore(env_path=env_path)
                snapshot = store.snapshot()
                if snapshot is not None:
                    if resolved_type is None:
                        resolved_type = snapshot.protocol
                    if resolved_model is None:
                        resolved_model = snapshot.model
                        if config_source == "DEFAULT":
                            config_source = "PERSISTED_PROFILE"
                    if resolved_base is None:
                        resolved_base = snapshot.endpoint
                    if resolved_key is None:
                        resolved_key = snapshot.api_key
            except Exception as exc:
                logger.debug(f"Could not load ProfileStore from {env_path}: {exc}")

        # 2. Check standard environment variables
        if resolved_type is None:
            resolved_type = os.environ.get("LLM_PROVIDER") or os.environ.get("PROVIDER_TYPE")
        if not resolved_type:
            if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
                resolved_type = "anthropic"
            else:
                resolved_type = "openai-compatible"

        if resolved_model is None:
            env_model = os.environ.get("LLM_MODEL") or os.environ.get("MODEL_ID")
            if env_model:
                resolved_model = env_model
                if config_source == "DEFAULT":
                    config_source = "ENVIRONMENT"
            else:
                resolved_model = ""

        if resolved_base is None:
            resolved_base = (
                os.environ.get("LLM_API_BASE")
                or os.environ.get("OPENAI_API_BASE")
                or os.environ.get("ANTHROPIC_API_BASE")
                or ""
            )

        if resolved_key is None:
            if resolved_type == "anthropic":
                resolved_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_API_KEY")
            else:
                resolved_key = (
                    os.environ.get("OPENAI_API_KEY")
                    or os.environ.get("LLM_API_KEY")
                    or os.environ.get("API_KEY")
                )

        if resolved_allow_keyless is None:
            env_keyless = (
                os.environ.get("LLM_ALLOW_KEYLESS") or os.environ.get("ALLOW_KEYLESS") or ""
            ).strip().lower()
            resolved_allow_keyless = env_keyless in ("1", "true", "yes")

        return cls(
            provider_type=resolved_type,
            model=resolved_model,
            api_base=resolved_base,
            api_key=resolved_key,
            requested_seed=requested_seed,
            provider_seed_supported=False,
            configuration_source=config_source,
            allow_keyless=resolved_allow_keyless,
        )

    @classmethod
    def from_env(
        cls,
        provider_type: str | None = None,
        model: str | None = None,
        api_base: str | None = None,
        requested_seed: int | None = None,
        allow_keyless: bool | None = None,
    ) -> RealLLMProviderConfig:
        """Alias for backward compatibility."""
        return cls.from_profile_or_env(
            provider_type=provider_type,
            model=model,
            api_base=api_base,
            requested_seed=requested_seed,
            allow_keyless=allow_keyless,
        )


class RealLLMProviderAdapter:
    """Production provider adapter implementing LLMProvider protocol for real inference.

    Compatible with both:
    - Pure LLM (LLMPlanner.decide)
    - Hybrid (HybridPlanner._plan_context)
    """

    def __init__(
        self,
        config: RealLLMProviderConfig | None = None,
        budget_guard: ProviderBudgetGuard | None = None,
        http_transport_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config or RealLLMProviderConfig.from_profile_or_env()
        self.budget_guard = budget_guard or ProviderBudgetGuard()
        self._http_factory = http_transport_factory
        self.call_history: list[dict[str, Any]] = []

    @property
    def model_name(self) -> str:
        return self.config.model or "unconfigured-model"

    @property
    def is_configured(self) -> bool:
        return self.config.is_configured

    @staticmethod
    def estimate_prompt_tokens(prompt: str) -> int:
        """Estimate token count client-side using cl100k_base or conservative character ratio.

        Note: Client-side estimation is inherently unauthoritative for arbitrary upstream
        endpoints (e.g. Gemini SentencePiece or proxy trajectory wrapping).
        """
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(prompt))
        except Exception:
            return max(1, (len(prompt) + 3) // 4)

    def complete(self, prompt: str) -> MeteredReviewResponse:
        """Execute model completion with controlled inference, budget guard, and token accounting."""
        if not self.is_configured:
            missing = []
            if not self.config.model:
                missing.append("model_id")
            if self.config.requires_api_key and not self.config.api_key:
                missing.append("api_key")
            raise RealProviderNotConfiguredError(
                f"REAL_LLM_BENCHMARK_BLOCKED: Real provider is not configured. Missing: {', '.join(missing)}. "
                "User must configure provider and model via model profile, environment variables, or CLI."
            )

        # 1. Check budget guard before initiating logical call
        self.budget_guard.record_logical_call()

        est_input = self.estimate_prompt_tokens(prompt)
        auth_input = self.config.authoritative_input_tokens

        # Pre-dispatch evaluation against strict token budget limits
        self.budget_guard.evaluate_pre_dispatch(
            estimated_input_tokens=est_input,
            reserved_output_tokens=self.config.max_output_tokens,
            authoritative_input_tokens=auth_input,
        )

        retries = 0
        last_exception: Exception | None = None

        while retries <= self.config.max_retries:
            # 2. Check HTTP attempt and spending ceiling (halts retry amplification)
            self.budget_guard.record_http_attempt()
            if retries > 0:
                self.budget_guard.record_retry(
                    estimated_input_tokens=est_input,
                    reserved_output_tokens=self.config.max_output_tokens,
                    authoritative_input_tokens=auth_input,
                )

            t0 = time.perf_counter()
            try:
                raw_text, usage_dict, latency_ms = self._dispatch_http_request(prompt)

                # Classify and extract usage
                token_usage = self._build_token_usage(usage_dict)

                in_tok = token_usage.input_uncached if token_usage else 0
                out_tok = token_usage.output_tokens if token_usage else 0
                total_tok = int(usage_dict.get("total_tokens") or 0) if usage_dict else (in_tok + out_tok)
                completion_details = usage_dict.get("completion_tokens_details") if isinstance(usage_dict, Mapping) else {}
                reasoning_tok = int(
                    (completion_details or {}).get("reasoning_tokens")
                    or (usage_dict.get("reasoning_tokens") if isinstance(usage_dict, Mapping) else 0)
                    or 0
                )

                # 3. Record success against budget limits
                self.budget_guard.record_success(
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    total_tokens=total_tok,
                    reasoning_tokens=reasoning_tok,
                )

                self.call_history.append({
                    "model": self.config.model,
                    "provider_type": self.config.provider_type,
                    "retries": retries,
                    "latency_ms": latency_ms,
                    "prompt_chars": len(prompt),
                    "response_chars": len(raw_text),
                    "tokens": dataclasses.asdict(token_usage) if token_usage else None,
                    "reasoning_tokens": reasoning_tok,
                    "total_tokens": total_tok,
                })

                return MeteredReviewResponse(review_json=raw_text, usage=token_usage)

            except CircuitBreakerTrippedError:
                # Do not retry if circuit breaker itself tripped
                raise

            except TimeoutError as exc:
                self.budget_guard.record_error()
                last_exception = exc
                retries += 1
                if retries <= self.config.max_retries:
                    sleep_sec = self.config.backoff_factor ** retries
                    time.sleep(sleep_sec)
                else:
                    raise RealProviderTimeoutError(f"Request timed out after {retries} attempts") from exc

            except RealProviderError as exc:
                self.budget_guard.record_error()
                last_exception = exc
                # Only retry on 429 rate limit or 5xx server errors
                if exc.status_code in (429, 500, 502, 503, 504):
                    retries += 1
                    if retries <= self.config.max_retries:
                        sleep_sec = self.config.backoff_factor ** retries
                        time.sleep(sleep_sec)
                        continue
                raise exc

            except Exception as exc:
                self.budget_guard.record_error()
                last_exception = exc
                retries += 1
                if retries <= self.config.max_retries:
                    sleep_sec = self.config.backoff_factor ** retries
                    time.sleep(sleep_sec)
                else:
                    raise RealProviderError(
                        f"Unexpected error communicating with provider: {type(exc).__name__}: {exc}"
                    ) from exc

        if last_exception:
            raise last_exception
        raise RealProviderError("Exceeded max retries without response")

    def _dispatch_http_request(self, prompt: str) -> tuple[str, dict[str, Any], float]:
        """Send HTTP POST request over standard loopback/HTTPS connection."""
        parsed = urllib.parse.urlsplit(self.config.api_base)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        is_https = parsed.scheme == "https"

        if self.config.provider_type == "anthropic":
            path = parsed.path.rstrip("/") + "/messages"
            payload_data: dict[str, Any] = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.config.max_output_tokens,
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
            }
        else:  # openai-compatible
            path = parsed.path.rstrip("/") + "/chat/completions"
            payload_data = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.config.max_output_tokens,
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "stream": False,
            }
            if self.config.provider_seed_supported and self.config.requested_seed is not None:
                payload_data["seed"] = self.config.requested_seed

        encoded_body = json.dumps(payload_data).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(encoded_body)),
        }

        if self.config.provider_type == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
            if self.config.api_key:
                headers["x-api-key"] = self.config.api_key
        else:
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

        t0 = time.perf_counter()
        conn = None
        try:
            if self._http_factory is not None:
                conn = self._http_factory(host, port, timeout=self.config.timeout_seconds)
            elif is_https:
                conn = http.client.HTTPSConnection(host, port, timeout=self.config.timeout_seconds)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=self.config.timeout_seconds)

            conn.request("POST", path, body=encoded_body, headers=headers)
            res = conn.getresponse()
            raw_bytes = res.read(65536)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            body_snippet = raw_bytes.decode("utf-8", errors="replace")[:256]
            if self.config.api_key and self.config.api_key in body_snippet:
                body_snippet = body_snippet.replace(self.config.api_key, "[REDACTED_API_KEY]")
            if res.status == 401 or res.status == 403:
                raise RealProviderError(
                    f"Authentication failure (HTTP {res.status}): {redact_secrets(body_snippet)}",
                    error_code="PROVIDER_AUTH_ERROR",
                    status_code=res.status,
                )
            if res.status == 429:
                raise RealProviderError(
                    f"Rate limit exceeded (HTTP 429): {redact_secrets(body_snippet)}",
                    error_code="PROVIDER_RATE_LIMIT",
                    status_code=429,
                )
            if res.status >= 500:
                raise RealProviderError(
                    f"Server error (HTTP {res.status}): {redact_secrets(body_snippet)}",
                    error_code=f"PROVIDER_HTTP_{res.status}",
                    status_code=res.status,
                )
            if res.status != 200:
                raise RealProviderError(
                    f"Unexpected status code {res.status}: {redact_secrets(body_snippet)}",
                    error_code=f"PROVIDER_HTTP_{res.status}",
                    status_code=res.status,
                )

            data = json.loads(raw_bytes.decode("utf-8"))

            if self.config.provider_type == "anthropic":
                content_blocks = data.get("content", [])
                text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
                usage = data.get("usage", {})
            else:
                choices = data.get("choices", [])
                if not choices:
                    raise RealProviderError("No choices returned from model", error_code="INVALID_PROVIDER_CONTENT")
                text = choices[0].get("message", {}).get("content", "")
                usage = data.get("usage", {})

            # Validate text does not echo the API key
            if self.config.api_key and self.config.api_key in text:
                raise RealProviderError("API key detected in model response text", error_code="SECURITY_VIOLATION")

            return text, usage, latency_ms

        except (TimeoutError, http.client.RemoteDisconnected) as exc:
            raise TimeoutError(f"Provider request timed out: {exc}") from exc
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _build_token_usage(self, usage_dict: Mapping[str, Any]) -> TokenUsage | None:
        """Construct structured TokenUsage from provider usage dict."""
        if not usage_dict or not isinstance(usage_dict, Mapping):
            return None

        provider = "anthropic" if self.config.provider_type == "anthropic" else "openai"
        api = "messages" if self.config.provider_type == "anthropic" else "chat_completions"

        input_tokens = int(usage_dict.get("prompt_tokens") or usage_dict.get("input_tokens") or 0)
        output_tokens = int(usage_dict.get("completion_tokens") or usage_dict.get("output_tokens") or 0)
        completion_details = usage_dict.get("completion_tokens_details") if isinstance(usage_dict, Mapping) else {}
        reasoning_tokens = int(
            (completion_details or {}).get("reasoning_tokens")
            or (usage_dict.get("reasoning_tokens") if isinstance(usage_dict, Mapping) else 0)
            or 0
        )

        effective_output = max(output_tokens, reasoning_tokens)
        safe_reasoning = min(reasoning_tokens, effective_output)

        # Sanitize identifiers for TokenUsage contract
        safe_response_id = f"resp-{int(time.time())}"
        safe_model = re.sub(r"[^A-Za-z0-9_.:-]", "-", self.config.model or "unknown-model")
        safe_tier = self.config.service_tier or "default"
        safe_region = self.config.region or "global"

        try:
            return TokenUsage(
                provider=provider,
                api=api,
                response_id=safe_response_id,
                model=safe_model,
                service_tier=safe_tier,
                region=safe_region,
                input_uncached=input_tokens,
                output_tokens=effective_output,
                reasoning_tokens=safe_reasoning,
            )
        except Exception as exc:
            logger.warning(f"Could not construct TokenUsage: {exc}")
            return None
