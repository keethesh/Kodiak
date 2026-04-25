"""
LiteLLM client implementation for Kodiak.

Uses LiteLLM to support OpenRouter and other providers with a unified interface.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from kodiak.services.base import LLMConfig, LLMResponse


class LiteLLMClient:
    """LiteLLM-based LLM client supporting OpenRouter and other providers."""
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._ensure_library_available()
    
    def _ensure_library_available(self) -> None:
        """Ensure litellm is installed."""
        try:
            import litellm
            self._litellm = litellm
        except ImportError:
            raise RuntimeError(
                "litellm is required but not installed. "
                "Install with: pip install litellm"
            )
    
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
        """
        Generate a response using LiteLLM.
        
        Args:
            model: Model identifier (e.g., 'anthropic/claude-3.5-sonnet')
            system_prompt: System instructions
            messages: Conversation history (OpenAI-style)
            tools: Optional tool definitions for function calling
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            response_format: Optional JSON schema for structured output
            
        Returns:
            LLMResponse with content, tool calls, and usage metadata
        """
        messages = self._prepare_messages(system_prompt, messages)
        
        completion_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "user": "kodiak-agent",
        }
        
        if tools:
            completion_kwargs["tools"] = tools
        
        if response_format:
            completion_kwargs["response_format"] = response_format
        
        if self.config.api_key:
            completion_kwargs["api_key"] = self.config.api_key
        
        if self.config.base_url:
            completion_kwargs["base_url"] = self.config.base_url
        
        try:
            response = await self._litellm.acompletion(**completion_kwargs)
            return self._parse_response(response, model)
        except Exception as exc:
            logger.error(f"LiteLLM generation failed: {exc}")
            return LLMResponse(
                content="",
                tool_calls=[],
                finish_reason="error",
                model=model,
            )
    
    def _prepare_messages(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Prepare messages for LiteLLM, combining system prompt."""
        prepared = []
        
        if system_prompt:
            prepared.append({
                "role": "system",
                "content": system_prompt,
            })
        
        for msg in messages:
            role = str(msg.get("role", "user")).lower()
            content = msg.get("content", "")
            
            if role == "system":
                continue
            
            prepared_msg = {
                "role": role,
                "content": content,
            }
            
            if role == "assistant" and msg.get("tool_calls"):
                prepared_msg["tool_calls"] = msg["tool_calls"]
            
            if msg.get("tool_call_id"):
                prepared_msg["tool_call_id"] = msg["tool_call_id"]
                prepared_msg["role"] = "tool"
            
            prepared.append(prepared_msg)
        
        return prepared
    
    def _parse_response(
        self,
        response: Any,
        model: str,
    ) -> LLMResponse:
        """Parse LiteLLM response into standard format."""
        choice = response.choices[0]
        
        content = ""
        tool_calls: List[Dict[str, Any]] = []
        
        if hasattr(choice.message, "content") and choice.message.content:
            content = str(choice.message.content or "")
        
        if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                if hasattr(tc, "function"):
                    tool_calls.append({
                        "id": getattr(tc, "id", f"call_{id(tc)}"),
                        "type": "function",
                        "function": {
                            "name": getattr(tc.function, "name", ""),
                            "arguments": getattr(tc.function, "arguments", "{}"),
                        }
                    })
        
        usage = getattr(response, "usage", None) or {}
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        
        cost = float(getattr(response, "_response_cost", 0.0) or 0.0)
        
        finish_reason = str(getattr(choice, "finish_reason", "") or "").lower()
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            response_cost=cost,
            model=model,
        )


async def create_llm_client(
    provider: str = "openrouter",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> LiteLLMClient:
    """
    Factory function to create an LLM client.
    
    Args:
        provider: LLM provider ('openrouter', 'azure', 'ollama', etc.)
        api_key: API key for the provider
        model: Default model to use
        
    Returns:
        Configured LiteLLMClient instance
    """
    config = LLMConfig(
        provider=provider,
        api_key=api_key or "",
        base_url=_get_base_url(provider),
        model=model or _get_default_model(provider),
    )
    return LiteLLMClient(config)


def _get_base_url(provider: str) -> Optional[str]:
    """Get base URL for a provider."""
    base_urls = {
        "openrouter": "https://openrouter.ai/api/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "openai": "https://api.openai.com/v1",
        "azure": None,
    }
    return base_urls.get(provider.lower())


def _get_default_model(provider: str) -> str:
    """Get default model for a provider."""
    defaults = {
        "openrouter": "anthropic/claude-3.5-sonnet-20241022",
        "anthropic": "claude-3.5-sonnet-20241022",
        "openai": "gpt-4o",
        "azure": "gpt-4o",
    }
    return defaults.get(provider.lower(), "gpt-4o")
