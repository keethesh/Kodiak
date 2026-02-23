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
    if normalized in {"low", "medium", "high"}:
        return normalized
    return "high"


def resolve_gemini_thinking_level(model_string: str, configured_level: str) -> str:
    configured = str(configured_level or "").strip().lower()
    if configured in {"low", "medium", "high"}:
        return configured
    model = str(model_string or "").lower()
    if "flash" in model:
        return "low"
    return "high"

