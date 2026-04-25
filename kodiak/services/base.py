"""
LLM Provider abstraction layer for Kodiak.

Supports multiple LLM providers through a unified interface.
Currently supports OpenRouter via LiteLLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    tool_calls: List[Dict[str, Any]]
    finish_reason: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    response_cost: float = 0.0
    model: str = ""


class LLMProvider(Protocol):
    """Protocol for LLM providers."""
    
    async def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Generate a response from the LLM."""
        ...


@dataclass 
class LLMConfig:
    """Configuration for LLM providers."""
    provider: str = "openrouter"
    api_key: str = ""
    base_url: Optional[str] = None
    model: str = "anthropic/claude-3.5-sonnet-20241022"
    temperature: float = 1.0
    max_tokens: int = 8192
    
    @classmethod
    def from_settings(cls, settings: Any) -> "LLMConfig":
        """Create config from Kodiak settings."""
        from kodiak.core.config import settings as kodiak_settings
        return cls(
            provider=kodiak_settings.llm_provider,
            api_key=kodiak_settings.get_resolved_api_key(),
            base_url=kodiak_settings.openrouter_base_url,
            model=kodiak_settings.llm_model,
            temperature=kodiak_settings.llm_temperature,
            max_tokens=kodiak_settings.llm_max_tokens,
        )
