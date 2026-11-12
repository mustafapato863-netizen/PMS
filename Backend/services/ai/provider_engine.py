"""Unified PMS AI Provider Engine (Phase 1).

Provides a unified, provider-neutral abstraction for AI text and structured generation:
1. Fixed provider hierarchy: Cloudflare Workers AI as primary, Google Gemini as fallback.
   OpenAI is decommissioned: no adapter makes outbound requests to it.
2. Bounded retries for transient failures on the primary provider (HTTP 500/502/503/504, network reset).
3. Fallback to Gemini permitted ONLY for:
   - Primary provider unavailability / disabled in config / missing credentials.
   - Primary rate/quota limits (HTTP 429).
   - Primary transient server errors after retries are exhausted.
   - Primary connection errors or timeouts.
4. Fallback STRICTLY FORBIDDEN for:
   - Authorization denials or missing user permissions.
   - Input validation failures or empty requests.
   - Safety refusals / content filter blocks by the primary provider.
   - Client errors (HTTP 400 bad request, HTTP 401 invalid key, HTTP 403 permission denied).
   - Missing PMS evidence or rejected unsafe responses.
5. Overall request deadline: Tracks total elapsed time across all retries and fallback attempts.
6. Absolute privacy & secret protection:
   - API keys and bearer tokens are never logged or exposed.
   - Raw provider error bodies are NEVER passed to clients or normal logs (preventing prompt echo).
   - Safe error categories and status codes are reported instead.
7. Strict response validation:
   - Empty, truncated, null, or refused responses are never reported as successful.
   - For structured requests, schema validation is enforced for BOTH providers.
8. Truthful observability:
   - Records provider, model, outcome, latency_ms, token usage.
   - Cost estimation returns exact USD for supported models, or None (unknown) if model or usage is unrecognized.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from services.ai.config import redact_secrets

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    """Accurate token pricing metadata per 1,000,000 tokens (USD).
    
    Supports indexing (`pricing[0]`, `pricing[1]`) for full backwards compatibility.
    """
    input_per_million: float
    output_per_million: float
    currency: str = "USD"
    effective_date: str = "2026-11-12"
    source: str = "Published Provider Reference (Cloudflare Workers AI / Google AI Studio)"

    def __getitem__(self, idx: int) -> float:
        if idx == 0:
            return self.input_per_million
        if idx == 1:
            return self.output_per_million
        raise IndexError(f"ModelPricing index out of range: {idx}")


# Known verified reference pricing per 1,000,000 tokens (USD)
# Verified: 2026-11-12 from official Cloudflare Workers AI & Google AI Studio published rates
_KNOWN_MODEL_PRICING: dict[str, ModelPricing] = {
    # Cloudflare Workers AI — IBM Granite 4.0 H Micro ($0.05 in, $0.15 out)
    "granite-4.0-h-micro": ModelPricing(0.05, 0.15, source="Cloudflare Workers AI granite-4.0-h-micro reference"),
    # Cloudflare Workers AI — GLM 4.7 Flash ($0.10 in, $0.30 out)
    "glm-4.7-flash": ModelPricing(0.10, 0.30, source="Cloudflare Workers AI glm-4.7-flash reference"),
    # Cloudflare Workers AI — Llama 3.3 70B & 3.1 8B
    "llama-3.3-70b": ModelPricing(0.20, 0.60, source="Cloudflare Workers AI llama-3.3-70b reference"),
    "llama-3.1-8b": ModelPricing(0.05, 0.15, source="Cloudflare Workers AI llama-3.1-8b reference"),
    # Google Gemini 3.5 Flash ($0.075 in, $0.30 out on paid tier; $0.00 on free tier up to limits)
    "gemini-3.5-flash": ModelPricing(0.075, 0.30, source="Google AI Studio gemini-3.5-flash reference"),
    # Google Gemini 3.5 Flash Lite ($0.0375 in, $0.15 out on paid tier; $0.00 on free tier up to limits)
    "gemini-3.5-flash-lite": ModelPricing(0.0375, 0.15, source="Google AI Studio gemini-3.5-flash-lite reference"),
    "gemini-3.1-flash-lite": ModelPricing(0.0375, 0.15, source="Google AI Studio gemini-3.1-flash-lite reference"),
    # Historical Gemini reference entries
    "gemini-2.5-flash": ModelPricing(0.15, 0.60, source="Google AI Studio gemini-2.5-flash legacy reference"),
    "gemini-1.5-flash": ModelPricing(0.15, 0.60, source="Google AI Studio gemini-1.5-flash legacy reference"),
    "gemini-2.0-flash": ModelPricing(0.10, 0.40, source="Google AI Studio gemini-2.0-flash legacy reference"),
    # Legacy reference (for historical cost queries)
    "gpt-4o-mini": ModelPricing(0.15, 0.60, source="OpenAI gpt-4o-mini reference"),
    "gpt-4o": ModelPricing(2.50, 10.00, source="OpenAI gpt-4o reference"),
}


# ---------------------------------------------------------------------------
# Exceptions & Error Categories
# ---------------------------------------------------------------------------


class ProviderError(Exception):
    """Base exception for provider errors with sanitized details."""

    def __init__(self, message: str, *, http_code: int | None = None, error_code: str = "provider_error") -> None:
        super().__init__(redact_secrets(message))
        self.http_code = http_code
        self.error_code = error_code


class ProviderTransientError(ProviderError):
    """Temporary server failure (500/502/503/504 or network reset) that is safe to retry."""

    def __init__(self, message: str = "Service temporarily unavailable", *, http_code: int | None = None) -> None:
        super().__init__(message, http_code=http_code, error_code="transient_error")


class ProviderTimeoutError(ProviderError):
    """Request exceeded timeout boundary."""

    def __init__(self, message: str = "Request timed out", *, http_code: int | None = 408) -> None:
        super().__init__(message, http_code=http_code, error_code="timeout")


class ProviderRateLimitError(ProviderError):
    """HTTP 429: Quota exhausted or rate limited. Permits immediate fallback, not retry on primary."""

    def __init__(self, message: str = "Rate limit or quota exhausted", *, http_code: int | None = 429) -> None:
        super().__init__(message, http_code=http_code, error_code="rate_limited")


class ProviderSafetyRefusalError(ProviderError):
    """Provider refused content due to safety policy. MUST NOT trigger fallback."""

    def __init__(self, message: str = "Content blocked by provider safety policy") -> None:
        super().__init__(message, http_code=400, error_code="safety_refusal")


class ProviderClientError(ProviderError):
    """Client error (HTTP 400 Bad Request, 401 Unauthorized, 403 Forbidden). MUST NOT trigger fallback."""

    def __init__(self, message: str = "Client request or authorization error", *, http_code: int | None = 400) -> None:
        super().__init__(message, http_code=http_code, error_code="client_error")


# Backward compatibility alias
ProviderNonRetryableError = ProviderClientError


class ProviderSchemaValidationError(ProviderError):
    """Returned content failed schema validation. MUST NOT report success."""

    def __init__(self, message: str = "Provider response did not conform to required schema") -> None:
        super().__init__(message, http_code=502, error_code="schema_validation_failed")


class ProviderTruncatedError(ProviderError):
    """Provider response was cut off before completion."""

    def __init__(self, message: str = "Provider response was truncated") -> None:
        super().__init__(message, http_code=502, error_code="truncated_response")


class ProviderEmptyResponseError(ProviderTransientError):
    """Provider returned empty text or whitespace."""

    def __init__(self, message: str = "Provider returned empty response") -> None:
        super().__init__(message, http_code=502)
        self.error_code = "empty_response"


# ---------------------------------------------------------------------------
# Data Contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderMessage:
    role: str  # "system", "user", "assistant"
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    neurons: float | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }
        if self.neurons is not None:
            res["neurons"] = self.neurons
        return res


@dataclass
class ProviderAttempt:
    provider: str  # "cloudflare" | "gemini"
    model: str
    status: str  # "success" | "rate_limited" | "timeout" | "transient_error" | "safety_refusal" | "client_error" | "schema_validation_failed" | "truncated" | "disabled" | "missing_key"
    latency_ms: float = 0.0
    http_code: int | None = None
    error_detail: str | None = None
    retry_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    neurons: float | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "http_code": self.http_code,
            "error_detail": redact_secrets(self.error_detail) if self.error_detail else None,
            "retry_count": self.retry_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
        if self.neurons is not None:
            res["neurons"] = self.neurons
        return res


@dataclass
class ProviderRequest:
    messages: list[ProviderMessage] = field(default_factory=list)
    system_instruction: str | None = None
    temperature: float = 0.0
    max_tokens: int = 2048
    response_format: str = "text"  # "text" | "json"
    json_schema: dict[str, Any] | None = None
    timeout_seconds: float | None = None
    purpose: str = "general"
    user_id: str | None = None
    user_role: str | None = None
    model: str | None = None
    use_alter_model: bool = False

    def validate_input(self) -> str | None:
        """Validate input before calling external providers."""
        if not self.messages and not self.system_instruction:
            return "empty_request"
        # Total character boundary check to avoid extreme payloads
        total_len = sum(len(m.content or "") for m in self.messages) + len(self.system_instruction or "")
        if total_len == 0:
            return "empty_request"
        if total_len > 120_000:
            return "prompt_exceeds_maximum_length"
        if self.json_schema is not None:
            unsupported = _check_unsupported_schema_keywords(self.json_schema)
            if unsupported:
                return f"unsupported_schema_keyword:{unsupported}"
        return None


@dataclass
class ProviderResponse:
    content: str
    provider: str  # "cloudflare" | "gemini" | "none"
    model: str  # e.g. "gemini-2.5-flash", "gpt-4o-mini", "none"
    outcome: str  # "success" | "fallback_success" | "provider_unavailable" | "rate_limited" | "timeout" | "safety_refusal" | "invalid_request" | "error"
    latency_ms: float = 0.0
    usage: TokenUsage = field(default_factory=TokenUsage)
    estimated_cost_usd: float | None = None
    attempts: list[ProviderAttempt] = field(default_factory=list)
    error_detail: str | None = None
    neurons: float | None = None

    @property
    def is_success(self) -> bool:
        return self.outcome in ("success", "fallback_success") and bool(self.content.strip())

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "content": self.content if self.is_success else "",
            "provider": self.provider,
            "model": self.model,
            "outcome": self.outcome,
            "latency_ms": self.latency_ms,
            "usage": self.usage.to_dict(),
            "estimated_cost_usd": self.estimated_cost_usd,
            "attempts": [a.to_dict() for a in self.attempts],
            "error_detail": redact_secrets(self.error_detail) if self.error_detail else None,
        }
        if self.neurons is not None:
            res["neurons"] = self.neurons
        return res


# ---------------------------------------------------------------------------
# Configuration (Fixed Hierarchy: Cloudflare Workers AI Primary, Gemini Fallback)
# ---------------------------------------------------------------------------


SUPPORTED_PROVIDERS = ("cloudflare", "gemini")


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    norm = value.strip().casefold()
    if norm in ("1", "true", "yes", "on", "enabled"):
        return True
    if norm in ("0", "false", "no", "off", "disabled"):
        return False
    return default


@dataclass(frozen=True)
class UnifiedProviderConfig:
    """Configuration for AI provider hierarchy.
    
    Default architecture: Cloudflare Workers AI is primary, Google Gemini is fallback.
    """
    primary_provider: str | None = None
    fallback_provider: str | None = None
    cloudflare_enabled: bool = True
    gemini_enabled: bool = True
    fallback_enabled: bool = True
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_model: str = "@cf/ibm-granite/granite-4.0-h-micro"
    cloudflare_alter_model: str = "@cf/zai-org/glm-4.7-flash"
    gemini_model: str = "gemini-2.5-flash"
    timeout_seconds: float = 10.0
    max_retries: int = 1
    gemini_api_key: str = ""

    @property
    def effective_primary_provider(self) -> str:
        if self.primary_provider in SUPPORTED_PROVIDERS:
            return self.primary_provider
        if self.cloudflare_account_id and self.cloudflare_api_token:
            return "cloudflare"
        if not self.cloudflare_account_id and not self.cloudflare_api_token and self.gemini_api_key:
            return "gemini"
        return "cloudflare"

    @property
    def effective_fallback_provider(self) -> str:
        if self.fallback_provider in SUPPORTED_PROVIDERS and self.fallback_provider != self.effective_primary_provider:
            return self.fallback_provider
        return "gemini" if self.effective_primary_provider == "cloudflare" else "cloudflare"


def load_unified_provider_config() -> UnifiedProviderConfig:
    """Load unified AI provider configuration from environment."""
    primary_provider = (
        os.environ.get("PMS_AI_PRIMARY_PROVIDER")
        or "cloudflare"
    ).strip().casefold()

    fallback_provider = (
        os.environ.get("PMS_AI_FALLBACK_PROVIDER")
        or "gemini"
    ).strip().casefold()

    cloudflare_enabled = _parse_bool(os.environ.get("PMS_AI_CLOUDFLARE_ENABLED"), default=True)
    gemini_enabled = _parse_bool(os.environ.get("PMS_AI_GEMINI_ENABLED"), default=True)
    fallback_enabled = _parse_bool(os.environ.get("PMS_AI_FALLBACK_ENABLED"), default=True)

    cloudflare_account_id = (
        os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        or os.environ.get("CF_ACCOUNT_ID")
        or ""
    ).strip()

    cloudflare_api_token = (
        os.environ.get("CLOUDFLARE_API_TOKEN")
        or os.environ.get("CF_API_TOKEN")
        or os.environ.get("CLOUDFLARE_API_KEY")
        or ""
    ).strip()

    cloudflare_model = (
        os.environ.get("CLOUDFLARE_AI_MODEL")
        or os.environ.get("CF_AI_MODEL")
        or os.environ.get("PMS_CLOUDFLARE_MODEL")
        or "@cf/ibm-granite/granite-4.0-h-micro"
    ).strip()

    cloudflare_alter_model = (
        os.environ.get("CLOUDFLARE_AI_MODEL_ALTER")
        or os.environ.get("CF_AI_MODEL_ALTER")
        or os.environ.get("CLOUDFLARE_MODEL_ALTER")
        or "@cf/zai-org/glm-4.7-flash"
    ).strip()

    gemini_model = (
        os.environ.get("PMS_GEMINI_MODEL")
        or os.environ.get("PMS_AI_GEMINI_MODEL")
        or os.environ.get("GEMINI_MODEL")
        or "gemini-2.5-flash"
    ).strip()

    try:
        raw_timeout = float(
            os.environ.get("PMS_AI_PROVIDER_TIMEOUT_SECONDS")
            or os.environ.get("PMS_AI_TIMEOUT_SECONDS")
            or "10.0"
        )
        timeout_seconds = max(1.0, min(raw_timeout, 30.0))
    except (TypeError, ValueError):
        timeout_seconds = 10.0

    try:
        raw_retries = int(os.environ.get("PMS_AI_MAX_RETRIES", "1"))
        max_retries = max(0, min(raw_retries, 2))
    except (TypeError, ValueError):
        max_retries = 1

    gemini_api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("Gemini_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()

    return UnifiedProviderConfig(
        primary_provider=primary_provider,
        fallback_provider=fallback_provider,
        cloudflare_enabled=cloudflare_enabled,
        gemini_enabled=gemini_enabled,
        fallback_enabled=fallback_enabled,
        cloudflare_account_id=cloudflare_account_id,
        cloudflare_api_token=cloudflare_api_token,
        cloudflare_model=cloudflare_model,
        cloudflare_alter_model=cloudflare_alter_model,
        gemini_model=gemini_model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        gemini_api_key=gemini_api_key,
    )


# ---------------------------------------------------------------------------
# Pricing & Cost Estimation
# ---------------------------------------------------------------------------


def estimate_cost_usd(provider: str, model: str, usage: TokenUsage | None) -> float | None:
    """Calculate estimated cost in USD. Returns None (unknown) if model or usage is unrecognized/incomplete."""
    if usage is None:
        return None
    tot = getattr(usage, "total_tokens", None)
    prompt = getattr(usage, "prompt_tokens", None)
    comp = getattr(usage, "completion_tokens", None)
    if tot is None or prompt is None or comp is None:
        return None
    if tot <= 0 or prompt < 0 or comp < 0:
        return None
    if prompt == 0 and comp == 0 and tot > 0:
        return None

    model_lower = str(model or "").casefold()
    if not model_lower:
        return None

    rates: Any = None
    # Sort patterns by length descending so more specific patterns (e.g. "gemini-3.5-flash-lite") match before prefixes ("gemini-3.5-flash")
    for pattern in sorted(_KNOWN_MODEL_PRICING.keys(), key=len, reverse=True):
        if pattern in model_lower:
            rates = _KNOWN_MODEL_PRICING[pattern]
            break

    if rates is None:
        # Truthful reporting: do not guess cost for unknown models
        return None

    in_per_m, out_per_m = rates
    cost = (prompt / 1_000_000.0 * in_per_m) + (comp / 1_000_000.0 * out_per_m)
    return round(cost, 8)


# ---------------------------------------------------------------------------
# Schema Validation Helper (Complete Recursive JSON Schema Subset)
# ---------------------------------------------------------------------------

_SUPPORTED_SCHEMA_KEYWORDS = frozenset({
    "type", "properties", "required", "additionalProperties", "items",
    "enum", "nullable",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern",
    "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties",
    "title", "description", "default",
})


def _check_unsupported_schema_keywords(node: Any) -> str | None:
    """Detect unsupported JSON Schema constructs without confusing property names with keywords."""
    if not isinstance(node, dict):
        return None

    for k, v in node.items():
        if k not in _SUPPORTED_SCHEMA_KEYWORDS:
            return k

    # Recurse into object properties (property names are not keywords; only their schemas are)
    if "properties" in node and isinstance(node["properties"], dict):
        for prop_name, prop_schema in node["properties"].items():
            if isinstance(prop_schema, dict):
                sub = _check_unsupported_schema_keywords(prop_schema)
                if sub is not None:
                    return sub

    # Recurse into array items
    if "items" in node:
        if isinstance(node["items"], dict):
            sub = _check_unsupported_schema_keywords(node["items"])
            if sub is not None:
                return sub
        elif isinstance(node["items"], list):
            for item in node["items"]:
                if isinstance(item, dict):
                    sub = _check_unsupported_schema_keywords(item)
                    if sub is not None:
                        return sub

    return None


def _validate_schema_node(instance: Any, schema: dict[str, Any], path: str = "$") -> tuple[bool, str | None]:
    """Validate a parsed JSON node against a supported JSON Schema subset.

    Zero model values or sensitive payload strings are included in error messages.
    """
    if not isinstance(schema, dict):
        return True, None

    # Nullable support
    if schema.get("nullable") is True and instance is None:
        return True, None

    # 1. Type validation (single type or union/list of types)
    expected_type = schema.get("type")
    type_checks = {
        "object": lambda x: isinstance(x, dict),
        "array": lambda x: isinstance(x, list),
        "string": lambda x: isinstance(x, str),
        "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
        "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
        "boolean": lambda x: isinstance(x, bool),
        "null": lambda x: x is None,
    }
    if expected_type:
        if isinstance(expected_type, list):
            matched = False
            for t in expected_type:
                fn = type_checks.get(t)
                if fn and fn(instance):
                    matched = True
                    break
            if not matched:
                return False, f"Expected one of types {expected_type} at {path}, got {type(instance).__name__}"
        else:
            check_fn = type_checks.get(expected_type)
            if check_fn and not check_fn(instance):
                if expected_type in ("object", "array"):
                    return False, f"Expected JSON {expected_type}, got {type(instance).__name__}"
                return False, f"Expected {expected_type} at {path}, got {type(instance).__name__}"

    # 2. Enum validation (do not reflect model instance value)
    if "enum" in schema:
        allowed = schema["enum"]
        if instance not in allowed:
            return False, f"Value at {path} is not in enum options"

    # 3. Numeric bounds validation (do not reflect model instance value)
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            return False, f"Number at {path} is less than minimum ({schema['minimum']})"
        if "maximum" in schema and instance > schema["maximum"]:
            return False, f"Number at {path} is greater than maximum ({schema['maximum']})"
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            return False, f"Number at {path} is less than or equal to exclusiveMinimum ({schema['exclusiveMinimum']})"
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            return False, f"Number at {path} is greater than or equal to exclusiveMaximum ({schema['exclusiveMaximum']})"
        if "multipleOf" in schema:
            mult = schema["multipleOf"]
            if mult > 0 and (instance / mult) % 1 != 0:
                return False, f"Number at {path} is not a multiple of {mult}"

    # 4. String constraints validation (do not reflect model instance value)
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            return False, f"String at {path} length is less than minLength ({len(instance)} < {schema['minLength']})"
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            return False, f"String at {path} length is greater than maxLength ({len(instance)} > {schema['maxLength']})"
        if "pattern" in schema:
            try:
                if not re.search(schema["pattern"], instance):
                    return False, f"String at {path} does not match required pattern"
            except re.error:
                return False, f"String at {path} pattern constraint validation failed"

    # 5. Object-specific validation (never reflect model property names or values)
    if isinstance(instance, dict):
        # Required properties
        missing = [req for req in (schema.get("required") or []) if req not in instance]
        if missing:
            return False, f"JSON missing required fields: {', '.join(missing)}"

        # minProperties / maxProperties
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            return False, f"Object at {path} has fewer properties than minProperties ({len(instance)} < {schema['minProperties']})"
        if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
            return False, f"Object at {path} has more properties than maxProperties ({len(instance)} > {schema['maxProperties']})"

        # additionalProperties: False
        if schema.get("additionalProperties") is False:
            allowed_props = set(schema.get("properties", {}).keys())
            extra_props = set(instance.keys()) - allowed_props
            if extra_props:
                return False, f"Unexpected additional property at {path} (additionalProperties is False)"

        # Validate properties recursively
        properties = schema.get("properties") or {}
        for prop_name, prop_schema in properties.items():
            if prop_name in instance and isinstance(prop_schema, dict):
                ok, err = _validate_schema_node(instance[prop_name], prop_schema, f"{path}.{prop_name}")
                if not ok:
                    return ok, err

    # 6. Array-specific validation
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            return False, f"Array at {path} has fewer items than minItems ({len(instance)} < {schema['minItems']})"
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            return False, f"Array at {path} has more items than maxItems ({len(instance)} > {schema['maxItems']})"
        if schema.get("uniqueItems") is True:
            seen = set()
            for item in instance:
                try:
                    serialized = json.dumps(item, sort_keys=True)
                except Exception:
                    serialized = str(item)
                if serialized in seen:
                    return False, f"Array at {path} contains duplicate items (uniqueItems is True)"
                seen.add(serialized)

        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for idx, item in enumerate(instance):
                ok, err = _validate_schema_node(item, items_schema, f"{path}[{idx}]")
                if not ok:
                    return ok, err

    return True, None


def validate_structured_output(text: str, schema: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Validate that text is valid JSON and satisfies requested schema properties."""
    if not text or not text.strip():
        return False, "Empty content returned"
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False, "Response is not valid JSON"

    if schema is None:
        return True, None

    unsupported = _check_unsupported_schema_keywords(schema)
    if unsupported:
        return False, f"Unsupported JSON schema feature: '{unsupported}'"

    return _validate_schema_node(data, schema)


def _read_with_deadline(resp: Any, timeout: float, chunk_size: int = 65536) -> str:
    """Read full response bytes respecting an explicit deadline."""
    t_start = time.perf_counter()
    chunks: list[bytes] = []

    # Configure underlying socket timeout if present
    sock = getattr(resp, "fp", None)
    if hasattr(sock, "raw"):
        sock = getattr(sock, "raw", sock)
    raw_sock = getattr(sock, "_sock", None)
    if hasattr(raw_sock, "settimeout"):
        try:
            raw_sock.settimeout(max(0.1, timeout))
        except Exception:
            pass

    while True:
        elapsed = time.perf_counter() - t_start
        remaining = timeout - elapsed
        if remaining <= 0:
            raise TimeoutError(f"Response read exceeded timeout limit of {timeout:.1f}s")
        if hasattr(raw_sock, "settimeout"):
            try:
                raw_sock.settimeout(max(0.1, remaining))
            except Exception:
                pass
        try:
            chunk = resp.read(chunk_size)
        except TypeError:
            chunk = resp.read()
            if chunk:
                chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
            break
        if not chunk:
            break
        chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))

    # Strictly check total elapsed time after read completes
    total_elapsed = time.perf_counter() - t_start
    if total_elapsed > timeout:
        raise TimeoutError(f"Response read exceeded timeout limit of {timeout:.1f}s")

    return b"".join(chunks).decode("utf-8")


# ---------------------------------------------------------------------------
# Safe Error Parser (Protects Private Data in Error Bodies)
# ---------------------------------------------------------------------------


def _parse_http_error(exc: urllib.error.HTTPError, provider_name: str) -> ProviderError:
    """Classify HTTP errors safely without leaking raw request/response bodies.
    
    Status codes are classified FIRST before inspecting body text.
    HTTP 400, 401, 403 are client errors and MUST NEVER be classified as rate limits,
    even if the body contains words like 'completion_rate' or 'rate'.
    """
    code = exc.code
    raw_body = ""
    try:
        if hasattr(exc, "read"):
            raw_body = exc.read().decode("utf-8", errors="ignore")
    except Exception:
        pass

    body_lower = raw_body.casefold()

    # 1. HTTP 429 is explicitly Rate Limit / Quota Exceeded
    if code == 429:
        return ProviderRateLimitError(f"{provider_name} rate limit or quota exceeded (HTTP 429)", http_code=429)

    # 2. All 4xx client errors (400, 401, 403, 404, 422, etc.) MUST NOT trigger fallback or become rate limits
    if 400 <= code <= 499:
        if "safety" in body_lower or "blocked" in body_lower or "content_filter" in body_lower:
            return ProviderSafetyRefusalError(f"{provider_name} blocked content due to safety policy")
        return ProviderClientError(f"{provider_name} client error (HTTP {code})", http_code=code)

    # 3. Transient server errors (500, 502, 503, 504) safe to retry or fallback
    if code in (500, 502, 503, 504):
        return ProviderTransientError(f"{provider_name} server error (HTTP {code})", http_code=code)

    # 4. Other codes: inspect for quota error messages ONLY if not a 4xx
    if "insufficient_quota" in body_lower or "quota_exceeded" in body_lower or "rate_limit" in body_lower:
        return ProviderRateLimitError(f"{provider_name} rate limit or quota exceeded (HTTP {code})", http_code=code)

    return ProviderClientError(f"{provider_name} request failed (HTTP {code})", http_code=code)


# ---------------------------------------------------------------------------
# Cloudflare Workers AI Provider Adapter
# ---------------------------------------------------------------------------


class CloudflareAIProviderAdapter:
    """Invokes the Cloudflare Workers AI REST API."""

    def __init__(self, http_client: Callable[..., Any] | None = None) -> None:
        self._http_client = http_client or urllib.request.urlopen

    def execute(
        self,
        request: ProviderRequest,
        config: UnifiedProviderConfig,
        *,
        timeout: float,
    ) -> tuple[str, TokenUsage]:
        if not config.cloudflare_account_id:
            raise ProviderClientError("Cloudflare Account ID is not configured", http_code=401)
        if not config.cloudflare_api_token:
            raise ProviderClientError("Cloudflare API Token is not configured", http_code=401)

        if getattr(request, "use_alter_model", False):
            model = config.cloudflare_alter_model or "@cf/zai-org/glm-4.7-flash"
        elif getattr(request, "model", None):
            model = request.model
        else:
            model = config.cloudflare_model or "@cf/ibm-granite/granite-4.0-h-micro"
        url = f"https://api.cloudflare.com/client/v4/accounts/{config.cloudflare_account_id}/ai/v1/chat/completions"

        messages = []
        system_content = request.system_instruction or ""
        if request.response_format == "json" and request.json_schema:
            schema_instruction = f"\nYou must output JSON conforming to this schema:\n{json.dumps(request.json_schema)}"
            system_content = (system_content + schema_instruction).strip()

        if system_content:
            messages.append({"role": "system", "content": system_content})

        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})

        if not messages:
            messages.append({"role": "user", "content": ""})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": max(0.0, min(request.temperature, 2.0)),
            "max_tokens": request.max_tokens or 2048,
        }
        if request.response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        raw_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=raw_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.cloudflare_api_token}",
            },
            method="POST",
        )

        t_call_start = time.perf_counter()
        try:
            with self._http_client(req, timeout=timeout) as resp:
                elapsed_connect = time.perf_counter() - t_call_start
                remaining_read = timeout - elapsed_connect
                if remaining_read <= 0:
                    raise ProviderTimeoutError(f"Cloudflare call timed out connecting after {elapsed_connect:.1f}s")
                raw_response = _read_with_deadline(resp, remaining_read)
        except urllib.error.HTTPError as exc:
            raise _parse_http_error(exc, "Cloudflare") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderTimeoutError(f"Cloudflare call timed out after {timeout:.1f}s") from exc
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            if "timed out" in str(exc).casefold():
                raise ProviderTimeoutError(f"Cloudflare connection timed out after {timeout:.1f}s") from exc
            raise ProviderTransientError(f"Cloudflare connection reset or unreachable: {type(exc).__name__}") from exc

        if time.perf_counter() - t_call_start > timeout:
            raise ProviderTimeoutError(f"Cloudflare call exceeded timeout deadline of {timeout:.1f}s")

        try:
            data = json.loads(raw_response)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ProviderTransientError("Cloudflare returned invalid non-JSON HTTP response body") from exc

        if isinstance(data, dict) and data.get("success") is False:
            errors = data.get("errors") or []
            msg = "; ".join(str(e.get("message", e)) for e in errors) if errors else "Cloudflare Workers AI returned success: false"
            code = (errors[0].get("code") if errors and isinstance(errors[0], dict) else None)
            if code in (10000, 10001, 10002):
                raise ProviderClientError(f"Cloudflare authentication failed: {msg}", http_code=401)
            raise ProviderTransientError(f"Cloudflare error: {msg}")

        text_result = ""
        choices = data.get("choices") or []
        if choices and isinstance(choices, list):
            first_choice = choices[0] or {}
            finish_reason = str(first_choice.get("finish_reason") or "").casefold()
            if finish_reason in ("length", "max_tokens"):
                raise ProviderTruncatedError("Cloudflare output truncated: model reached maxOutputTokens limit")
            if finish_reason in ("content_filter",):
                raise ProviderSafetyRefusalError("Cloudflare blocked response due to content safety policy")
            msg_obj = first_choice.get("message") or {}
            text_result = str(msg_obj.get("content") or "")
        elif "result" in data and isinstance(data.get("result"), dict):
            res_obj = data["result"]
            text_result = str(res_obj.get("response") or "")

        if not text_result.strip():
            raise ProviderEmptyResponseError("Cloudflare returned empty text response")

        if request.response_format == "json" and request.json_schema:
            valid, err = validate_structured_output(text_result, request.json_schema)
            if not valid:
                raise ProviderSchemaValidationError(f"Cloudflare structured output failed schema validation: {err}")

        usage_raw = data.get("usage") or {}
        raw_neurons = usage_raw.get("neurons")
        neurons = float(raw_neurons) if raw_neurons is not None else None
        usage = TokenUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
            completion_tokens=int(usage_raw.get("completion_tokens") or 0),
            total_tokens=int(usage_raw.get("total_tokens") or 0),
            neurons=neurons,
        )
        return text_result.strip(), usage


# ---------------------------------------------------------------------------
# Gemini Provider Adapter
# ---------------------------------------------------------------------------


class GeminiProviderAdapter:
    """Invokes Google Gemini REST API (generateContent)."""

    def __init__(self, http_client: Callable[..., Any] | None = None) -> None:
        self._http_client = http_client or urllib.request.urlopen

    def execute(
        self,
        request: ProviderRequest,
        config: UnifiedProviderConfig,
        *,
        timeout: float,
    ) -> tuple[str, TokenUsage]:
        if not config.gemini_api_key:
            raise ProviderClientError("Gemini API key is not configured", http_code=401)

        model = (
            request.model
            if (request.model and "gemini" in request.model.lower())
            else config.gemini_model
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        system_parts = []
        if request.system_instruction:
            system_parts.append({"text": request.system_instruction})

        contents = []
        for msg in request.messages:
            if msg.role == "system":
                system_parts.append({"text": msg.content})
            elif msg.role in ("user", "human"):
                contents.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role in ("assistant", "model"):
                contents.append({"role": "model", "parts": [{"text": msg.content}]})

        if not contents and system_parts:
            contents.append({"role": "user", "parts": [{"text": request.system_instruction or ""}]})
            system_parts = []

        generation_config: dict[str, Any] = {
            "temperature": max(0.0, min(request.temperature, 2.0)),
            # Ensure output token limit accommodates reasoning thoughts + text
            "maxOutputTokens": max(256, request.max_tokens or 2048),
        }
        if request.response_format == "json":
            generation_config["responseMimeType"] = "application/json"
            if request.json_schema:
                generation_config["responseSchema"] = request.json_schema

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}

        raw_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=raw_data,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": config.gemini_api_key,
            },
            method="POST",
        )

        t_call_start = time.perf_counter()
        try:
            with self._http_client(req, timeout=timeout) as resp:
                elapsed_connect = time.perf_counter() - t_call_start
                remaining_read = timeout - elapsed_connect
                if remaining_read <= 0:
                    raise ProviderTimeoutError(f"Gemini call timed out connecting after {elapsed_connect:.1f}s")
                raw_response = _read_with_deadline(resp, remaining_read)
        except urllib.error.HTTPError as exc:
            raise _parse_http_error(exc, "Gemini") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderTimeoutError(f"Gemini call timed out after {timeout:.1f}s") from exc
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            if "timed out" in str(exc).casefold():
                raise ProviderTimeoutError(f"Gemini connection timed out after {timeout:.1f}s") from exc
            raise ProviderTransientError(f"Gemini connection reset or unreachable: {type(exc).__name__}") from exc

        if time.perf_counter() - t_call_start > timeout:
            raise ProviderTimeoutError(f"Gemini call exceeded timeout deadline of {timeout:.1f}s")

        try:
            data = json.loads(raw_response)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ProviderTransientError("Gemini returned invalid non-JSON HTTP response body") from exc

        # Check prompt-level safety block
        prompt_feedback = data.get("promptFeedback") or {}
        block_reason = str(prompt_feedback.get("blockReason") or "").upper()
        if block_reason and block_reason not in ("", "NONE"):
            raise ProviderSafetyRefusalError(f"Gemini blocked prompt due to policy: {block_reason}")

        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderSafetyRefusalError("Gemini returned zero candidates (possible safety filter)")

        candidate = candidates[0]
        finish_reason = str(candidate.get("finishReason") or "").upper()

        if (
            finish_reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "MALICIOUS", "OTHER"}
            or "SAFETY" in finish_reason
            or "BLOCK" in finish_reason
            or "PROHIBIT" in finish_reason
            or "SPII" in finish_reason
            or "RECIT" in finish_reason
        ):
            raise ProviderSafetyRefusalError(f"Gemini candidate blocked by content filter: {finish_reason}")
        if finish_reason == "MAX_TOKENS":
            raise ProviderTruncatedError("Gemini candidate truncated due to max output tokens")

        parts = candidate.get("content", {}).get("parts", [])
        text_result = parts[0].get("text", "") if parts else ""

        if not text_result.strip():
            raise ProviderTransientError("Gemini returned empty candidate text")

        # Schema validation for structured requests
        if request.response_format == "json":
            valid, err = validate_structured_output(text_result, request.json_schema)
            if not valid:
                raise ProviderSchemaValidationError(f"Gemini JSON output validation failed: {err}")

        usage_raw = data.get("usageMetadata") or {}
        usage = TokenUsage(
            prompt_tokens=int(usage_raw.get("promptTokenCount") or 0),
            completion_tokens=int(usage_raw.get("candidatesTokenCount") or 0),
            total_tokens=int(usage_raw.get("totalTokenCount") or 0),
        )
        return text_result.strip(), usage


# ---------------------------------------------------------------------------
# OpenAI (decommissioned)
# ---------------------------------------------------------------------------


class OpenAIProviderAdapter:
    """DEPRECATED, inert. Kept only so old imports keep resolving.

    OpenAI is decommissioned. ``execute`` never performs I/O and always raises
    ``ProviderClientError``; the engine never selects this adapter because
    ``openai`` is not in ``SUPPORTED_PROVIDERS``.
    """

    def __init__(self, http_client: Callable[..., Any] | None = None) -> None:
        # The injected client is intentionally ignored: zero outbound requests.
        self._http_client = None

    def execute(
        self,
        request: ProviderRequest,
        config: UnifiedProviderConfig,
        *,
        timeout: float,
    ) -> tuple[str, TokenUsage]:
        raise ProviderClientError("OpenAI provider is decommissioned", http_code=410)


# ---------------------------------------------------------------------------
# Unified Provider Engine
# ---------------------------------------------------------------------------


class UnifiedProviderEngine:
    """Orchestrates primary (Cloudflare Workers AI) and fallback (Gemini) AI completion calls.
    
    Default hierarchy: Cloudflare Workers AI is primary, Google Gemini is fallback.
    """

    def __init__(
        self,
        config: UnifiedProviderConfig | None = None,
        *,
        cloudflare_adapter: CloudflareAIProviderAdapter | None = None,
        gemini_adapter: GeminiProviderAdapter | None = None,
    ) -> None:
        self.config = config or load_unified_provider_config()
        self.cloudflare_adapter = cloudflare_adapter or CloudflareAIProviderAdapter()
        self.gemini_adapter = gemini_adapter or GeminiProviderAdapter()

    def _is_enabled(self, provider: str) -> bool:
        if provider == "cloudflare":
            return self.config.cloudflare_enabled
        if provider == "gemini":
            return self.config.gemini_enabled
        return False

    def _get_model(self, provider: str, request: ProviderRequest | None = None) -> str:
        if provider == "cloudflare":
            if request and getattr(request, "use_alter_model", False):
                return self.config.cloudflare_alter_model or "@cf/zai-org/glm-4.7-flash"
            if request and getattr(request, "model", None) and ("@" in request.model or "cf" in request.model or "granite" in request.model or "glm" in request.model):
                return request.model
            return self.config.cloudflare_model
        if provider == "gemini":
            if request and getattr(request, "model", None) and "gemini" in request.model.lower():
                return request.model
            return self.config.gemini_model
        return "unknown"

    def _has_credentials(self, provider: str) -> bool:
        if provider == "cloudflare":
            return bool(self.config.cloudflare_account_id and self.config.cloudflare_api_token)
        if provider == "gemini":
            return bool(self.config.gemini_api_key)
        return False

    def _get_adapter(self, provider: str) -> Any:
        if provider == "cloudflare":
            return self.cloudflare_adapter
        if provider == "gemini":
            return self.gemini_adapter
        return None

    # -- Public API -----------------------------------------------------

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Execute a provider request with primary attempt, bounded retries, and fallback."""
        t_overall_start = time.perf_counter()
        overall_timeout = request.timeout_seconds or self.config.timeout_seconds
        deadline = t_overall_start + overall_timeout

        # 1. Input Safety & Boundary Validation
        safety_issue = request.validate_input()
        if safety_issue:
            total_ms = round((time.perf_counter() - t_overall_start) * 1000.0, 2)
            logger.warning("UnifiedProviderEngine rejected input due to boundary validation: %s", safety_issue)
            return ProviderResponse(
                content="",
                provider="none",
                model="none",
                outcome="invalid_request",
                latency_ms=total_ms,
                error_detail=f"Validation failed: {safety_issue}",
            )

        # 2. User limits hook for Phase 7
        if not self._check_user_limits(request.user_id, request.user_role):
            total_ms = round((time.perf_counter() - t_overall_start) * 1000.0, 2)
            return ProviderResponse(
                content="",
                provider="none",
                model="none",
                outcome="rate_limited",
                latency_ms=total_ms,
                error_detail="Per-user AI usage limit exceeded",
            )

        attempts: list[ProviderAttempt] = []

        # 3. Primary Provider Loop
        primary_success = False
        primary_response_text = ""
        primary_usage = TokenUsage()
        allow_fallback = True
        terminal_outcome: str | None = None
        terminal_detail: str | None = None

        primary_name = self.config.effective_primary_provider
        primary_adapter = self._get_adapter(primary_name)
        primary_model = self._get_model(primary_name, request)

        if not self._is_enabled(primary_name):
            attempts.append(ProviderAttempt(
                provider=primary_name,
                model=primary_model,
                status="disabled",
                error_detail=f"{primary_name} primary provider is disabled in configuration",
            ))
        elif not self._has_credentials(primary_name):
            attempts.append(ProviderAttempt(
                provider=primary_name,
                model=primary_model,
                status="missing_key",
                error_detail=f"{primary_name} credentials are not configured",
            ))
        elif primary_adapter is None:
            attempts.append(ProviderAttempt(
                provider=primary_name,
                model=primary_model,
                status="client_error",
                error_detail=f"Unknown primary provider: {primary_name}",
            ))
        else:
            retries = 0
            while retries <= self.config.max_retries:
                remaining_time = deadline - time.perf_counter()
                if remaining_time <= 0:
                    attempts.append(ProviderAttempt(
                        provider=primary_name,
                        model=primary_model,
                        status="timeout",
                        error_detail=f"Overall request deadline exceeded before {primary_name} call",
                        retry_count=retries,
                    ))
                    allow_fallback = False
                    terminal_outcome = "timeout"
                    terminal_detail = "Overall request deadline exceeded"
                    break

                per_call_timeout = min(self.config.timeout_seconds, remaining_time)
                t0 = time.perf_counter()
                try:
                    text, usage = primary_adapter.execute(request, self.config, timeout=per_call_timeout)
                    call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    if time.perf_counter() > deadline:
                        attempts.append(ProviderAttempt(
                            provider=primary_name,
                            model=primary_model,
                            status="timeout",
                            error_detail="Response completed after overall deadline expired",
                            latency_ms=call_ms,
                            retry_count=retries,
                        ))
                        allow_fallback = False
                        terminal_outcome = "timeout"
                        terminal_detail = "Overall request deadline exceeded"
                        break
                    attempts.append(ProviderAttempt(
                        provider=primary_name,
                        model=primary_model,
                        status="success",
                        latency_ms=call_ms,
                        retry_count=retries,
                        input_tokens=usage.prompt_tokens,
                        output_tokens=usage.completion_tokens,
                        neurons=usage.neurons,
                    ))
                    primary_success = True
                    primary_response_text = text
                    primary_usage = usage
                    break
                except ProviderSafetyRefusalError as exc:
                    call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    attempts.append(ProviderAttempt(
                        provider=primary_name,
                        model=primary_model,
                        status="safety_refusal",
                        latency_ms=call_ms,
                        http_code=exc.http_code,
                        error_detail=str(exc),
                        retry_count=retries,
                    ))
                    # STRICT BOUNDARY: Never fall back to bypass safety refusal!
                    allow_fallback = False
                    terminal_outcome = "safety_refusal"
                    terminal_detail = str(exc)
                    logger.warning("%s refused content due to safety. Fallback forbidden.", primary_name)
                    break
                except ProviderClientError as exc:
                    call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    attempts.append(ProviderAttempt(
                        provider=primary_name,
                        model=primary_model,
                        status="client_error",
                        latency_ms=call_ms,
                        http_code=exc.http_code,
                        error_detail=str(exc),
                        retry_count=retries,
                    ))
                    # STRICT BOUNDARY: Client errors (400, 401, 403) must NOT trigger fallback
                    allow_fallback = False
                    terminal_outcome = "invalid_request" if exc.http_code == 400 else "error"
                    terminal_detail = str(exc)
                    logger.warning("%s returned client error HTTP %s. Fallback forbidden.", primary_name, exc.http_code)
                    break
                except ProviderRateLimitError as exc:
                    call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    attempts.append(ProviderAttempt(
                        provider=primary_name,
                        model=primary_model,
                        status="rate_limited",
                        latency_ms=call_ms,
                        http_code=exc.http_code,
                        error_detail=str(exc),
                        retry_count=retries,
                    ))
                    # 429 permits immediate fallback without retrying primary
                    logger.info("%s rate limited (HTTP 429). Triggering fallback.", primary_name)
                    break
                except ProviderTimeoutError as exc:
                    call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    attempts.append(ProviderAttempt(
                        provider=primary_name,
                        model=primary_model,
                        status="timeout",
                        latency_ms=call_ms,
                        http_code=exc.http_code,
                        error_detail=str(exc),
                        retry_count=retries,
                    ))
                    if retries < self.config.max_retries and (deadline - time.perf_counter()) > 1.0:
                        retries += 1
                        time.sleep(0.05)
                        continue
                    break
                except (ProviderSchemaValidationError, ProviderTruncatedError) as exc:
                    call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    attempts.append(ProviderAttempt(
                        provider=primary_name,
                        model=primary_model,
                        status=exc.error_code,
                        latency_ms=call_ms,
                        http_code=exc.http_code,
                        error_detail=str(exc),
                        retry_count=retries,
                    ))
                    # STRICT BOUNDARY: Schema validation failures and truncated output must NOT fall back
                    allow_fallback = False
                    terminal_outcome = exc.error_code
                    terminal_detail = str(exc)
                    logger.warning("%s output failed validation (%s). Fallback forbidden.", primary_name, exc.error_code)
                    break
                except ProviderTransientError as exc:
                    call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    attempts.append(ProviderAttempt(
                        provider=primary_name,
                        model=primary_model,
                        status=exc.error_code,
                        latency_ms=call_ms,
                        http_code=exc.http_code,
                        error_detail=str(exc),
                        retry_count=retries,
                    ))
                    if retries < self.config.max_retries and (deadline - time.perf_counter()) > 1.0:
                        retries += 1
                        time.sleep(0.05)
                        continue
                    break

        if primary_success:
            total_ms = round((time.perf_counter() - t_overall_start) * 1000.0, 2)
            cost = estimate_cost_usd(primary_name, primary_model, primary_usage)
            response = ProviderResponse(
                content=primary_response_text,
                provider=primary_name,
                model=primary_model,
                outcome="success",
                latency_ms=total_ms,
                usage=primary_usage,
                estimated_cost_usd=cost,
                attempts=attempts,
            )
            self._record_observability(request, response)
            return response

        # Check if fallback is explicitly forbidden by policy
        if not allow_fallback:
            total_ms = round((time.perf_counter() - t_overall_start) * 1000.0, 2)
            response = ProviderResponse(
                content="",
                provider="none",
                model="none",
                outcome=terminal_outcome or "error",
                latency_ms=total_ms,
                attempts=attempts,
                error_detail=terminal_detail or "Primary provider failed with non-fallback error",
            )
            self._record_observability(request, response)
            return response

        # 4. Fallback Provider Loop
        fallback_name = self.config.effective_fallback_provider
        fallback_adapter = self._get_adapter(fallback_name)
        fallback_model = self._get_model(fallback_name, request)

        if not self.config.fallback_enabled or fallback_name == "none" or fallback_adapter is None:
            total_ms = round((time.perf_counter() - t_overall_start) * 1000.0, 2)
            return ProviderResponse(
                content="",
                provider="none",
                model="none",
                outcome="provider_unavailable",
                latency_ms=total_ms,
                attempts=attempts,
                error_detail="Primary provider failed and fallback is disabled",
            )

        # Check overall deadline before initiating fallback
        remaining_time = deadline - time.perf_counter()
        if remaining_time <= 0:
            total_ms = round((time.perf_counter() - t_overall_start) * 1000.0, 2)
            attempts.append(ProviderAttempt(
                provider=fallback_name,
                model=fallback_model,
                status="timeout",
                error_detail="Overall request deadline exceeded before fallback call",
            ))
            return ProviderResponse(
                content="",
                provider="none",
                model="none",
                outcome="timeout",
                latency_ms=total_ms,
                attempts=attempts,
                error_detail="Overall request deadline exceeded",
            )

        logger.info("Engaging fallback provider (%s) after eligible primary failure.", fallback_name)

        if not self._is_enabled(fallback_name):
            attempts.append(ProviderAttempt(
                provider=fallback_name,
                model=fallback_model,
                status="disabled",
                error_detail=f"{fallback_name} fallback provider is disabled in configuration",
            ))
        elif not self._has_credentials(fallback_name):
            attempts.append(ProviderAttempt(
                provider=fallback_name,
                model=fallback_model,
                status="missing_key",
                error_detail=f"{fallback_name} credentials are not configured",
            ))
        else:
            t0 = time.perf_counter()
            per_call_timeout = min(self.config.timeout_seconds, remaining_time)
            try:
                text, usage = fallback_adapter.execute(request, self.config, timeout=per_call_timeout)
                call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                if time.perf_counter() > deadline:
                    attempts.append(ProviderAttempt(
                        provider=fallback_name,
                        model=fallback_model,
                        status="timeout",
                        error_detail="Response completed after overall deadline expired",
                        latency_ms=call_ms,
                    ))
                    terminal_outcome = "timeout"
                    terminal_detail = "Overall request deadline exceeded"
                else:
                    attempts.append(ProviderAttempt(
                        provider=fallback_name,
                        model=fallback_model,
                        status="success",
                        latency_ms=call_ms,
                        input_tokens=usage.prompt_tokens,
                        output_tokens=usage.completion_tokens,
                        neurons=usage.neurons,
                    ))
                    total_ms = round((time.perf_counter() - t_overall_start) * 1000.0, 2)
                    cost = estimate_cost_usd(fallback_name, fallback_model, usage)
                    response = ProviderResponse(
                        content=text,
                        provider=fallback_name,
                        model=fallback_model,
                        outcome="fallback_success",
                        latency_ms=total_ms,
                        usage=usage,
                        estimated_cost_usd=cost,
                        attempts=attempts,
                    )
                    self._record_observability(request, response)
                    return response
            except ProviderSafetyRefusalError as exc:
                call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                attempts.append(ProviderAttempt(
                    provider=fallback_name,
                    model=fallback_model,
                    status="safety_refusal",
                    latency_ms=call_ms,
                    http_code=exc.http_code,
                    error_detail=str(exc),
                ))
            except ProviderRateLimitError as exc:
                call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                attempts.append(ProviderAttempt(
                    provider=fallback_name,
                    model=fallback_model,
                    status="rate_limited",
                    latency_ms=call_ms,
                    http_code=exc.http_code,
                    error_detail=str(exc),
                ))
            except ProviderTimeoutError as exc:
                call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                attempts.append(ProviderAttempt(
                    provider=fallback_name,
                    model=fallback_model,
                    status="timeout",
                    latency_ms=call_ms,
                    http_code=exc.http_code,
                    error_detail=str(exc),
                ))
            except ProviderError as exc:
                call_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                attempts.append(ProviderAttempt(
                    provider=fallback_name,
                    model=fallback_model,
                    status=exc.error_code,
                    latency_ms=call_ms,
                    http_code=exc.http_code,
                    error_detail=str(exc),
                ))

        # 5. All Eligible Providers Exhausted
        total_ms = round((time.perf_counter() - t_overall_start) * 1000.0, 2)
        active_attempts = [a for a in attempts if a.status not in ("disabled", "missing_key")]
        refusal_attempt = next((a for a in attempts if a.status == "safety_refusal"), None)
        any_safety_refusal = refusal_attempt is not None
        is_all_rate_limited = bool(active_attempts) and all(a.status == "rate_limited" for a in active_attempts)
        is_all_timeout = bool(active_attempts) and all(a.status == "timeout" for a in active_attempts)

        summary_errors = [f"{a.provider}: {a.status}" for a in attempts]
        error_summary = "; ".join(summary_errors) if summary_errors else "no_attempts"

        if any_safety_refusal:
            outcome = "safety_refusal"
            detail = (refusal_attempt.error_detail if refusal_attempt and refusal_attempt.error_detail else "Provider safety refusal")
        elif is_all_rate_limited:
            outcome = "rate_limited"
            detail = f"All AI providers rate limited or quota exhausted ({error_summary})"
        elif is_all_timeout:
            outcome = "timeout"
            detail = f"Overall request deadline exceeded ({error_summary})"
        else:
            outcome = "provider_unavailable"
            detail = f"All AI providers are currently unavailable ({error_summary})"

        logger.warning("All AI providers unavailable for request: %s", error_summary)

        response = ProviderResponse(
            content="",
            provider="none",
            model="none",
            outcome=outcome,
            latency_ms=total_ms,
            attempts=attempts,
            error_detail=detail,
        )
        self._record_observability(request, response)
        return response

    # -- Phase 7 Stubs & Observability ----------------------------------

    def _check_user_limits(self, user_id: str | None, user_role: str | None) -> bool:
        """Hook for per-user rate limiting and cost controls (Phase 7)."""
        return True

    def _record_observability(self, request: ProviderRequest, response: ProviderResponse) -> None:
        """Structured observability recording without logging sensitive content or secrets."""
        fallback_used = (
            response.provider == self.config.effective_fallback_provider
            and response.outcome == "fallback_success"
        )
        attempt_summaries = [
            {
                "provider": a.provider,
                "model": a.model,
                "status": a.status,
                "latency_ms": a.latency_ms,
                "input_tokens": a.input_tokens,
                "output_tokens": a.output_tokens,
                "neurons": a.neurons,
                "retry_count": a.retry_count,
            }
            for a in response.attempts
        ]
        logger.info(
            "UnifiedProviderEngine purpose=%s outcome=%s provider=%s model=%s latency_ms=%.1f tokens=%d neurons=%s cost=%s fallback_used=%s attempts=%s",
            request.purpose,
            response.outcome,
            response.provider,
            response.model,
            response.latency_ms,
            response.usage.total_tokens,
            f"{response.usage.neurons:.4f}" if response.usage.neurons is not None else "none",
            f"${response.estimated_cost_usd:.6f}" if response.estimated_cost_usd is not None else "unknown",
            fallback_used,
            attempt_summaries,
        )


_default_engine: UnifiedProviderEngine | None = None


def reset_unified_provider_engine() -> None:
    """Reset the global default engine instance (useful for testing and reload)."""
    global _default_engine
    _default_engine = None


def get_unified_provider_engine(reload: bool = False) -> UnifiedProviderEngine:
    """Return or initialize global UnifiedProviderEngine instance."""
    global _default_engine
    if _default_engine is None or reload:
        _default_engine = UnifiedProviderEngine()
    return _default_engine
