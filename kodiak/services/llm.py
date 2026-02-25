"""
Gemini model utilities for Kodiak.
"""

from __future__ import annotations

import os
from typing import Final


ALLOWED_GEMINI_MODELS: Final[tuple[str, str]] = (
    "gemini/gemini-3.1-pro-preview",
    "gemini/gemini-3-flash-preview",
)

# Pricing per 1M tokens (USD). Input/output/thinking/cached billed separately.
# cached = discounted rate for context-cache hits (25% of input price).
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gemini/gemini-3.1-pro-preview": {"input": 1.25, "output": 10.00, "thinking": 3.50, "cached": 0.3125},
    "gemini/gemini-3-flash-preview":  {"input": 0.15, "output": 0.60,  "thinking": 3.50, "cached": 0.0375},
}


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    """Return estimated USD cost for a given token usage and model.

    ``input_tokens`` is the full prompt_token_count (which includes cached tokens).
    ``cached_tokens`` are re-billed at the cheaper cached rate instead of the
    full input rate, so we subtract them from the non-cached input bucket.
    """
    pricing = _MODEL_PRICING.get(model) or _MODEL_PRICING["gemini/gemini-3.1-pro-preview"]
    non_cached_input = max(0, input_tokens - cached_tokens)
    return (
        (non_cached_input  / 1_000_000) * pricing["input"]
        + (cached_tokens   / 1_000_000) * pricing["cached"]
        + (output_tokens   / 1_000_000) * pricing["output"]
        + (thinking_tokens / 1_000_000) * pricing["thinking"]
    )


def normalize_model_name(model_string: str) -> str:
    """
    Normalize supported Gemini model names to `gemini/<model-id>` form.
    Raises ValueError for unsupported models.
    """
    raw = str(model_string or "").strip()
    if not raw:
        raise ValueError("KODIAK_LLM_MODEL is required")

    normalized = raw
    if not raw.startswith("gemini/"):
        normalized = f"gemini/{raw}"

    if normalized not in ALLOWED_GEMINI_MODELS:
        allowed = ", ".join(ALLOWED_GEMINI_MODELS)
        raise ValueError(
            f"Unsupported model '{raw}'. Supported models: {allowed}"
        )
    return normalized


def validate_model_name(model_string: str) -> bool:
    try:
        normalize_model_name(model_string)
        return True
    except ValueError:
        return False


def get_google_api_key() -> str:
    """
    Resolve Google API key from settings/env.
    Backward compatible with KODIAK_LLM_API_KEY as a fallback.
    """
    from kodiak.core.config import settings

    key = settings.google_api_key or settings.llm_api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("KODIAK_LLM_API_KEY")
    if not key:
        raise ValueError("GOOGLE_API_KEY is required for Gemini")
    return str(key)


def normalize_gemini_thinking_level(level: str) -> str:
    normalized = str(level or "").strip().lower()
    # "minimal" is a valid level for Gemini Flash models
    if normalized in {"minimal", "low", "medium", "high"}:
        return normalized
    return "high"


def resolve_gemini_thinking_level(model_string: str, configured_level: str) -> str:
    configured = str(configured_level or "").strip().lower()
    model = str(model_string or "").lower()
    is_flash = "flash" in model
    # Flash supports minimal/low/medium/high; Pro supports low/medium/high
    valid = {"minimal", "low", "medium", "high"} if is_flash else {"low", "medium", "high"}
    if configured in valid:
        return configured
    # Default: Flash → "low" (cost-efficient); Pro → "high" (best reasoning)
    return "low" if is_flash else "high"

