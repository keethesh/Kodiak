"""
Configuration management for Kodiak

Supports multiple LLM providers including OpenAI, Gemini, Claude, and others
through LiteLLM with flexible environment-based configuration.
"""

import os
from typing import Optional, Dict, Any
from pydantic import BaseSettings, Field
from enum import Enum


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    GEMINI = "gemini"
    CLAUDE = "claude"
    OLLAMA = "ollama"
    AZURE = "azure"
    COHERE = "cohere"
    HUGGINGFACE = "huggingface"


class KodiakSettings(BaseSettings):
    """Kodiak application settings"""
    
    # Database Configuration
    postgres_server: str = Field(default="localhost", env="POSTGRES_SERVER")
    postgres_user: str = Field(default="kodiak", env="POSTGRES_USER")
    postgres_password: str = Field(default="kodiak_password", env="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="kodiak_db", env="POSTGRES_DB")
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")
    
    # LLM Configuration
    llm_provider: LLMProvider = Field(default=LLMProvider.GEMINI, env="KODIAK_LLM_PROVIDER")
    llm_model: str = Field(default="gemini/gemini-1.5-pro", env="KODIAK_LLM_MODEL")
    llm_api_key: Optional[str] = Field(default=None, env="KODIAK_LLM_API_KEY")
    llm_base_url: Optional[str] = Field(default=None, env="KODIAK_LLM_BASE_URL")
    llm_temperature: float = Field(default=0.1, env="KODIAK_LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=4096, env="KODIAK_LLM_MAX_TOKENS")
    
    # Legacy environment variable support
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, env="GOOGLE_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    
    # Application Configuration
    debug: bool = Field(default=False, env="KODIAK_DEBUG")
    log_level: str = Field(default="INFO", env="KODIAK_LOG_LEVEL")
    
    # Security Configuration
    enable_safety_checks: bool = Field(default=True, env="KODIAK_ENABLE_SAFETY")
    max_concurrent_agents: int = Field(default=5, env="KODIAK_MAX_AGENTS")
    
    # Tool Configuration
    tool_timeout: int = Field(default=300, env="KODIAK_TOOL_TIMEOUT")  # 5 minutes
    enable_hive_mind: bool = Field(default=True, env="KODIAK_ENABLE_HIVE_MIND")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def database_url(self) -> str:
        """Get the database URL"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def async_database_url(self) -> str:
        """Get the async database URL"""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
    
    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration for LiteLLM"""
        config = {
            "model": self.llm_model,
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
        }
        
        # Determine API key based on provider
        api_key = self.llm_api_key
        if not api_key:
            if self.llm_provider == LLMProvider.OPENAI:
                api_key = self.openai_api_key
            elif self.llm_provider == LLMProvider.GEMINI:
                api_key = self.google_api_key
            elif self.llm_provider == LLMProvider.CLAUDE:
                api_key = self.anthropic_api_key
        
        if api_key:
            config["api_key"] = api_key
        
        if self.llm_base_url:
            config["api_base"] = self.llm_base_url
        
        return config
    
    def get_model_display_name(self) -> str:
        """Get a human-readable model name"""
        model_map = {
            "gemini/gemini-1.5-pro": "Gemini 1.5 Pro",
            "gemini/gemini-1.5-flash": "Gemini 1.5 Flash",
            "openai/gpt-4": "GPT-4",
            "openai/gpt-4-turbo": "GPT-4 Turbo",
            "openai/gpt-3.5-turbo": "GPT-3.5 Turbo",
            "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet",
            "claude-3-opus-20240229": "Claude 3 Opus",
        }
        return model_map.get(self.llm_model, self.llm_model)


# Global settings instance
settings = KodiakSettings()


# LLM Model presets for easy configuration
LLM_PRESETS = {
    # Gemini Models
    "gemini-pro": {
        "provider": LLMProvider.GEMINI,
        "model": "gemini/gemini-1.5-pro",
        "description": "Google Gemini 1.5 Pro - Excellent for complex reasoning and code analysis"
    },
    "gemini-flash": {
        "provider": LLMProvider.GEMINI,
        "model": "gemini/gemini-1.5-flash",
        "description": "Google Gemini 1.5 Flash - Fast and efficient for most tasks"
    },
    
    # OpenAI Models
    "gpt-4": {
        "provider": LLMProvider.OPENAI,
        "model": "openai/gpt-4",
        "description": "OpenAI GPT-4 - High-quality reasoning and analysis"
    },
    "gpt-4-turbo": {
        "provider": LLMProvider.OPENAI,
        "model": "openai/gpt-4-turbo",
        "description": "OpenAI GPT-4 Turbo - Faster GPT-4 with larger context"
    },
    "gpt-3.5-turbo": {
        "provider": LLMProvider.OPENAI,
        "model": "openai/gpt-3.5-turbo",
        "description": "OpenAI GPT-3.5 Turbo - Fast and cost-effective"
    },
    
    # Claude Models
    "claude-sonnet": {
        "provider": LLMProvider.CLAUDE,
        "model": "claude-3-5-sonnet-20241022",
        "description": "Anthropic Claude 3.5 Sonnet - Excellent for security analysis"
    },
    "claude-opus": {
        "provider": LLMProvider.CLAUDE,
        "model": "claude-3-opus-20240229",
        "description": "Anthropic Claude 3 Opus - Most capable Claude model"
    },
}


def get_available_models() -> Dict[str, Dict[str, Any]]:
    """Get all available model presets"""
    return LLM_PRESETS


def configure_for_gemini(api_key: str, model: str = "gemini/gemini-1.5-pro") -> Dict[str, str]:
    """
    Get environment variables for Gemini configuration
    
    Args:
        api_key: Your Google API key
        model: Gemini model to use (default: gemini/gemini-1.5-pro)
    
    Returns:
        Dictionary of environment variables to set
    """
    return {
        "KODIAK_LLM_PROVIDER": "gemini",
        "KODIAK_LLM_MODEL": model,
        "GOOGLE_API_KEY": api_key,
        "KODIAK_LLM_TEMPERATURE": "1",
        "KODIAK_LLM_MAX_TOKENS": "4096"
    }


def configure_for_openai(api_key: str, model: str = "openai/gpt-4") -> Dict[str, str]:
    """
    Get environment variables for OpenAI configuration
    
    Args:
        api_key: Your OpenAI API key
        model: OpenAI model to use (default: openai/gpt-4)
    
    Returns:
        Dictionary of environment variables to set
    """
    return {
        "KODIAK_LLM_PROVIDER": "openai",
        "KODIAK_LLM_MODEL": model,
        "OPENAI_API_KEY": api_key,
        "KODIAK_LLM_TEMPERATURE": "0.1",
        "KODIAK_LLM_MAX_TOKENS": "4096"
    }


def configure_for_claude(api_key: str, model: str = "claude-3-5-sonnet-20241022") -> Dict[str, str]:
    """
    Get environment variables for Claude configuration
    
    Args:
        api_key: Your Anthropic API key
        model: Claude model to use (default: claude-3-5-sonnet-20241022)
    
    Returns:
        Dictionary of environment variables to set
    """
    return {
        "KODIAK_LLM_PROVIDER": "claude",
        "KODIAK_LLM_MODEL": model,
        "ANTHROPIC_API_KEY": api_key,
        "KODIAK_LLM_TEMPERATURE": "0.1",
        "KODIAK_LLM_MAX_TOKENS": "4096"
    }