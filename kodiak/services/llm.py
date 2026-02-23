"""
LLM Service for Kodiak

Provides utility functions for LLM provider inference and API key management.
These functions are shared between config validation and agent code.
"""

from typing import Optional, Dict, Any


def infer_provider_from_model(model_string: str) -> str:
    """Infer provider from LiteLLM model string format"""
    if "/" in model_string:
        prefix = model_string.split("/")[0]
        return prefix
    else:
        # Handle models without prefix (legacy or special cases)
        if model_string.startswith("gpt"):
            return "openai"
        elif model_string.startswith("claude"):
            return "anthropic"
        elif model_string.startswith("gemini"):
            return "gemini"
        else:
            raise ValueError(f"Cannot infer provider from model string: {model_string}")


def is_gemini_provider(provider: str) -> bool:
    normalized = str(provider or "").strip().lower()
    return normalized in {"gemini", "vertex_ai"}


def normalize_gemini_thinking_level(level: str) -> str:
    normalized = str(level or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    return "high"


def resolve_gemini_thinking_level(model_string: str, configured_level: str) -> str:
    configured = str(configured_level or "").strip().lower()
    if configured in {"low", "medium", "high"}:
        return configured
    # Safe default split for Gemini 3 families.
    model = str(model_string or "").lower()
    if "flash" in model:
        return "low"
    return "high"


def build_gemini_extra_body(thinking_level: str) -> Dict[str, Any]:
    return {
        "google": {
            "thinking_config": {
                "thinking_level": normalize_gemini_thinking_level(thinking_level)
            }
        }
    }


def get_api_key_for_provider(provider: str) -> Optional[str]:
    """Get the appropriate API key for the provider from settings"""
    from kodiak.core.config import settings
    
    key_mapping = {
        "openai": settings.openai_api_key,
        "gemini": settings.google_api_key,
        "anthropic": settings.anthropic_api_key,
        "vertex_ai": settings.google_api_key,
        "azure": settings.openai_api_key,  # Azure uses OpenAI format
        "cohere": None,  # Add when supported
        "huggingface": None,  # Add when supported
        "ollama": None,  # Local models don't need API keys
    }
    return key_mapping.get(provider)


def get_required_api_key_env_var(provider: str) -> str:
    """Get the required environment variable name for the provider"""
    env_var_mapping = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GOOGLE_API_KEY", 
        "anthropic": "ANTHROPIC_API_KEY",
        "vertex_ai": "GOOGLE_API_KEY",
        "azure": "OPENAI_API_KEY",
        "cohere": "COHERE_API_KEY",
        "huggingface": "HUGGINGFACE_API_KEY",
        "ollama": None,  # Local models don't need API keys
    }
    return env_var_mapping.get(provider, "KODIAK_LLM_API_KEY")
