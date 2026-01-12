"""
LLM Service for Kodiak

Provides a unified interface for interacting with different LLM providers
through LiteLLM, with support for any LiteLLM-compatible model string.
"""

import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
from loguru import logger
import litellm
from litellm import acompletion, completion

from kodiak.core.config import settings


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


def get_api_key_for_provider(provider: str) -> Optional[str]:
    """Get the appropriate API key for the provider"""
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


class LLMService:
    """Service for interacting with LLM providers"""
    
    def __init__(self):
        self.model = settings.llm_model
        
        # Infer or use explicit provider
        if hasattr(settings, 'llm_provider') and settings.llm_provider:
            # Handle both string and enum values for backward compatibility during transition
            if hasattr(settings.llm_provider, 'value'):
                self.provider = settings.llm_provider.value
            else:
                self.provider = str(settings.llm_provider)
        else:
            self.provider = infer_provider_from_model(self.model)
        
        # Get API key for provider
        self.api_key = get_api_key_for_provider(self.provider)
        
        # Configure LiteLLM with minimal setup
        litellm.set_verbose = settings.debug
        
        # Set API keys in environment for LiteLLM
        self._configure_litellm_keys()
        
        logger.info(f"LLM Service initialized with model: {self.model} (provider: {self.provider})")
    
    def _configure_litellm_keys(self):
        """Configure API keys for LiteLLM"""
        if settings.openai_api_key:
            litellm.openai_key = settings.openai_api_key
        if settings.google_api_key:
            litellm.vertex_project = None  # Will use GOOGLE_API_KEY
            litellm.vertex_location = None
        if settings.anthropic_api_key:
            litellm.anthropic_key = settings.anthropic_api_key
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get chat completion from the configured LLM
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max tokens
            stream: Whether to stream the response
            **kwargs: Additional parameters for the LLM
        
        Returns:
            LLM response dictionary
        """
        try:
            # Prepare parameters - pass model string directly to LiteLLM
            params = {
                "model": self.model,  # Direct pass-through to LiteLLM
                "messages": messages,
                "temperature": temperature or settings.llm_temperature,
                "max_tokens": max_tokens or settings.llm_max_tokens,
                "stream": stream,
                **kwargs
            }
            
            # LiteLLM handles provider routing automatically based on model string
            if stream:
                return await self._stream_completion(params)
            else:
                response = await acompletion(**params)
                return response
                
        except Exception as e:
            # Propagate LiteLLM errors directly to user
            logger.error(f"LLM completion failed: {e}")
            raise
    
    async def _stream_completion(self, params: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream completion responses"""
        try:
            response = await acompletion(**params)
            async for chunk in response:
                yield chunk
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            raise
    
    async def generate_agent_response(
        self,
        system_prompt: str,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        skills: Optional[str] = None
    ) -> str:
        """
        Generate a response for an agent with system prompt and context
        
        Args:
            system_prompt: System prompt defining the agent's role
            user_message: User's message or task
            context: Additional context (scan results, previous actions, etc.)
            skills: Formatted skills string to inject into the prompt
        
        Returns:
            Generated response text
        """
        messages = []
        
        # Build system message
        system_content = system_prompt
        
        if skills:
            system_content += f"\n\n{skills}"
        
        if context:
            system_content += f"\n\nCONTEXT:\n{self._format_context(context)}"
        
        messages.append({
            "role": "system",
            "content": system_content
        })
        
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        try:
            response = await self.chat_completion(messages)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Agent response generation failed: {e}")
            return f"Error generating response: {str(e)}"
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context dictionary into a readable string"""
        formatted = []
        
        for key, value in context.items():
            if isinstance(value, dict):
                formatted.append(f"{key.upper()}:")
                for sub_key, sub_value in value.items():
                    formatted.append(f"  {sub_key}: {sub_value}")
            elif isinstance(value, list):
                formatted.append(f"{key.upper()}: {len(value)} items")
                for i, item in enumerate(value[:3]):  # Show first 3 items
                    formatted.append(f"  {i+1}. {item}")
                if len(value) > 3:
                    formatted.append(f"  ... and {len(value) - 3} more")
            else:
                formatted.append(f"{key.upper()}: {value}")
        
        return "\n".join(formatted)
    
    async def analyze_security_finding(
        self,
        finding_data: Dict[str, Any],
        target_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze a security finding using the LLM
        
        Args:
            finding_data: Raw finding data from security tools
            target_info: Information about the target being tested
        
        Returns:
            Analysis results with severity, impact, and recommendations
        """
        system_prompt = """You are a cybersecurity expert analyzing security findings. 
        Provide detailed analysis including:
        1. Severity assessment (Critical, High, Medium, Low, Info)
        2. Potential impact and exploitability
        3. Remediation recommendations
        4. Additional testing suggestions
        
        Be precise and actionable in your analysis."""
        
        user_message = f"""
        Analyze this security finding:
        
        FINDING DATA:
        {self._format_context(finding_data)}
        
        TARGET INFORMATION:
        {self._format_context(target_info)}
        
        Provide your analysis in JSON format with the following structure:
        {{
            "severity": "Critical|High|Medium|Low|Info",
            "confidence": "High|Medium|Low",
            "impact": "Description of potential impact",
            "exploitability": "Assessment of how easily this can be exploited",
            "remediation": ["List of remediation steps"],
            "additional_testing": ["Suggested follow-up tests"],
            "references": ["Relevant CVE, CWE, or other references"]
        }}
        """
        
        try:
            response = await self.generate_agent_response(system_prompt, user_message)
            
            # Try to parse JSON response
            import json
            try:
                analysis = json.loads(response)
                return analysis
            except json.JSONDecodeError:
                # If JSON parsing fails, return raw response
                return {
                    "severity": "Info",
                    "confidence": "Low",
                    "impact": "Analysis parsing failed",
                    "raw_analysis": response
                }
                
        except Exception as e:
            logger.error(f"Security finding analysis failed: {e}")
            return {
                "severity": "Info",
                "confidence": "Low",
                "impact": f"Analysis failed: {str(e)}",
                "error": str(e)
            }
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model configuration"""
        try:
            provider = self.provider
            api_key_configured = bool(self.api_key)
            
            return {
                "model": self.model,
                "provider": provider,
                "provider_source": "explicit" if (hasattr(settings, 'llm_provider') and settings.llm_provider) else "inferred",
                "api_key_configured": api_key_configured,
                "temperature": settings.llm_temperature,
                "max_tokens": settings.llm_max_tokens
            }
        except Exception as e:
            return {
                "model": self.model,
                "error": str(e),
                "api_key_configured": False
            }


# Global LLM service instance
llm_service = LLMService()


# Convenience functions
async def chat_completion(*args, **kwargs):
    """Convenience function for chat completion"""
    return await llm_service.chat_completion(*args, **kwargs)


async def generate_agent_response(*args, **kwargs):
    """Convenience function for agent response generation"""
    return await llm_service.generate_agent_response(*args, **kwargs)


async def analyze_security_finding(*args, **kwargs):
    """Convenience function for security finding analysis"""
    return await llm_service.analyze_security_finding(*args, **kwargs)