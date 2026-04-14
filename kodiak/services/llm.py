"""
LLM utilities for Kodiak (OpenRouter via LiteLLM).

Pricing is tracked from OpenRouter API response metadata.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional


SUPPORTED_MODELS = [
    "anthropic/claude-3.5-sonnet-20241022",
    "anthropic/claude-3.5-haiku-20241022",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "x-ai/grok-2",
    "google/gemini-2.0-flash-exp",
]


def normalize_model_name(model_string: str) -> str:
    """
    Normalize model name to OpenRouter format.
    """
    raw = str(model_string or "").strip()
    if not raw:
        raise ValueError("KODIAK_LLM_MODEL is required")

    if raw.startswith("gemini/"):
        return f"google/{raw.split('/', 1)[1]}"

    return raw


def validate_model_name(model_string: str) -> bool:
    """Check if model name is valid."""
    try:
        normalize_model_name(model_string)
        return True
    except ValueError:
        return False


def get_openrouter_api_key() -> str:
    """Get OpenRouter API key from settings/env."""
    from kodiak.core.config import settings

    key = (
        settings.openrouter_api_key
        or os.getenv("KODIAK_OPENROUTER_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )
    if not key:
        raise ValueError("KODIAK_OPENROUTER_API_KEY is required for OpenRouter")
    return str(key)


def get_openrouter_base_url() -> Optional[str]:
    """Get OpenRouter base URL from settings/env."""
    from kodiak.core.config import settings

    return (
        settings.openrouter_base_url
        or os.getenv("OPENROUTER_BASE_URL")
    )


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    """
    Calculate estimated USD cost for OpenRouter API calls.

    Note: OpenRouter returns actual cost in response metadata.
    This function provides estimates for planning purposes.

    For actual costs, use the response_cost field from LLMResponse.
    """
    cost_per_million = {
        "claude-3.5-sonnet": {"input": 3.0, "output": 15.0},
        "claude-3.5-haiku": {"input": 0.8, "output": 4.0},
        "gpt-4o": {"input": 2.5, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        "grok-2": {"input": 2.0, "output": 8.0},
        "gemini-2.0-flash": {"input": 0.0, "output": 0.0},
        "llama-3.1-70b": {"input": 0.65, "output": 2.75},
    }

    model_lower = model.lower()

    rate = {"input": 0.0, "output": 0.0}
    for key, prices in cost_per_million.items():
        if key in model_lower:
            rate = prices
            break

    non_cached_input = max(0, input_tokens - cached_tokens)

    return (
        (non_cached_input / 1_000_000) * rate["input"]
        + (cached_tokens / 1_000_000) * (rate["input"] * 0.25)
        + (output_tokens / 1_000_000) * rate["output"]
    )


def format_cost_summary(
    input_tokens: int,
    output_tokens: int,
    total_cost: float,
) -> str:
    """Format cost summary for display."""
    return (
        f"Tokens: {input_tokens:,} in / {output_tokens:,} out | "
        f"Est. Cost: ${total_cost:.4f}"
    )
