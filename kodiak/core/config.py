"""
Configuration management for Kodiak

Supports any LiteLLM-compatible model string with automatic provider inference
and simplified configuration validation.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from enum import Enum


# Error message templates for consistent error handling
ERROR_MESSAGES = {
    "missing_model": "KODIAK_LLM_MODEL is required. Example: gemini/gemini-3-pro-preview",
    "missing_api_key": "API key required for provider '{provider}': set {env_var}",
    "inference_failed": "Cannot infer provider from '{model}'. Set KODIAK_LLM_PROVIDER explicitly or use format 'provider/model'",
    "invalid_format": "Invalid model format '{model}'. Check LiteLLM documentation for supported formats: https://docs.litellm.ai/docs/providers"
}


# Import provider inference utilities from llm service
from kodiak.services.llm import (
    infer_provider_from_model,
    get_api_key_for_provider,
    get_required_api_key_env_var
)



class KodiakSettings(BaseSettings):
    """Kodiak application settings"""
    
    # Application Configuration
    PROJECT_NAME: str = Field(default="Kodiak", alias="KODIAK_PROJECT_NAME")
    VERSION: str = Field(default="1.0.0", alias="KODIAK_VERSION")
    
    # TUI Configuration
    tui_color_theme: str = Field(default="dark", alias="KODIAK_TUI_COLOR_THEME")
    tui_refresh_rate: int = Field(default=10, alias="KODIAK_TUI_REFRESH_RATE")  # Hz
    
    # Database Configuration
    # Database type: "sqlite" (default, zero-config) or "postgres" (production)
    db_type: str = Field(default="sqlite", alias="KODIAK_DB_TYPE")
    
    # SQLite Configuration (default, stored in ~/.kodiak/)
    sqlite_path: Optional[str] = Field(default=None, alias="KODIAK_SQLITE_PATH")
    
    # PostgreSQL Configuration (optional, for production deployments)
    postgres_server: str = Field(default="localhost", alias="POSTGRES_SERVER")
    postgres_user: str = Field(default="kodiak", alias="POSTGRES_USER")
    postgres_password: str = Field(default="kodiak_password", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="kodiak_db", alias="POSTGRES_DB")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    
    # LLM Configuration
    llm_model: str = Field(default="gemini/gemini-3-pro-preview", alias="KODIAK_LLM_MODEL")
    llm_api_key: Optional[str] = Field(default=None, alias="KODIAK_LLM_API_KEY")
    llm_base_url: Optional[str] = Field(default=None, alias="KODIAK_LLM_BASE_URL")
    llm_temperature: float = Field(default=0.1, alias="KODIAK_LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=4096, alias="KODIAK_LLM_MAX_TOKENS")
    
    # Legacy environment variable support
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    
    # Application Configuration
    debug: bool = Field(default=False, alias="KODIAK_DEBUG")
    log_level: str = Field(default="INFO", alias="KODIAK_LOG_LEVEL")
    
    # Security Configuration
    enable_safety_checks: bool = Field(default=True, alias="KODIAK_ENABLE_SAFETY")
    max_concurrent_agents: int = Field(default=5, alias="KODIAK_MAX_AGENTS")
    
    # Tool Configuration
    tool_timeout: int = Field(default=300, alias="KODIAK_TOOL_TIMEOUT")  # 5 minutes
    enable_hive_mind: bool = Field(default=True, alias="KODIAK_ENABLE_HIVE_MIND")
    memory_enabled: bool = Field(default=True, alias="KODIAK_MEMORY_ENABLED")
    memory_max_entries: int = Field(default=200, alias="KODIAK_MEMORY_MAX_ENTRIES")
    memory_recent_in_prompt: int = Field(default=10, alias="KODIAK_MEMORY_RECENT")
    memory_output_chars: int = Field(default=1500, alias="KODIAK_MEMORY_OUTPUT_CHARS")
    
    # Toolbox Container Configuration
    toolbox_image: str = Field(default="ghcr.io/keethesh/kodiak-toolbox:latest", alias="KODIAK_TOOLBOX_IMAGE")
    
    model_config = SettingsConfigDict(
        env_file=[
            ".env",  # Current directory
            str(Path.home() / ".kodiak" / "config.env"),  # User config from wizard
        ],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    def _get_default_sqlite_path(self) -> str:
        """Get the default SQLite database path in ~/.kodiak/"""
        from pathlib import Path
        kodiak_dir = Path.home() / ".kodiak"
        kodiak_dir.mkdir(exist_ok=True)
        return str(kodiak_dir / "kodiak.db")

    @property
    def database_url(self) -> str:
        """Get the database URL (sync driver)"""
        if self.db_type.lower() == "sqlite":
            db_path = self.sqlite_path or self._get_default_sqlite_path()
            return f"sqlite:///{db_path}"
        else:
            return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def async_database_url(self) -> str:
        """Get the async database URL"""
        if self.db_type.lower() == "sqlite":
            db_path = self.sqlite_path or self._get_default_sqlite_path()
            return f"sqlite+aiosqlite:///{db_path}"
        else:
            return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database"""
        return self.db_type.lower() == "sqlite"
    
    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration for LiteLLM"""
        config = {
            "model": self.llm_model,
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
        }
        
        # Determine API key based on provider
        # Use provider-specific API key resolution
        provider = infer_provider_from_model(self.llm_model)
        api_key_env = get_required_api_key_env_var(provider)
        
        api_key = None
        if api_key_env:
            # Map environment variable names to class attributes
            env_to_attr = {
                "GOOGLE_API_KEY": "google_api_key",
                "OPENAI_API_KEY": "openai_api_key", 
                "ANTHROPIC_API_KEY": "anthropic_api_key"
            }
            
            attr_name = env_to_attr.get(api_key_env)
            if attr_name and hasattr(self, attr_name):
                api_key = getattr(self, attr_name)
            
            # Fallback to environment variable
            if not api_key:
                api_key = os.getenv(api_key_env)
        
        if api_key:
            config["api_key"] = api_key
        
        if self.llm_base_url:
            config["api_base"] = self.llm_base_url
        
        return config
    
    def get_model_display_name(self) -> str:
        """Get a human-readable model name"""
        model_map = {
            "gemini/gemini-3-pro-preview": "Gemini 3 Pro",
            "gemini/gemini-3-flash-preview": "Gemini 3 Flash",
            "gemini/gemini-1.5-pro": "Gemini 1.5 Pro",
            "gemini/gemini-1.5-flash": "Gemini 1.5 Flash",
            "openai/gpt-4": "GPT-4",
            "openai/gpt-4-turbo": "GPT-4 Turbo",
            "openai/gpt-3.5-turbo": "GPT-3.5 Turbo",
            "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet",
            "claude-3-opus-20240229": "Claude 3 Opus",
        }
        return model_map.get(self.llm_model, self.llm_model)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get current model configuration info"""
        try:
            # Infer or use explicit provider
            if hasattr(self, 'llm_provider') and self.llm_provider:
                if hasattr(self.llm_provider, 'value'):
                    provider = self.llm_provider.value
                else:
                    provider = str(self.llm_provider)
                provider_source = "explicit"
            else:
                provider = infer_provider_from_model(self.llm_model)
                provider_source = "inferred"
            
            api_key_configured = bool(get_api_key_for_provider(provider, self))
            
            return {
                "model": self.llm_model,
                "provider": provider,
                "provider_source": provider_source,
                "api_key_configured": api_key_configured,
                "temperature": self.llm_temperature,
                "max_tokens": self.llm_max_tokens
            }
        except Exception as e:
            return {
                "model": self.llm_model,
                "error": str(e),
                "api_key_configured": False
            }
    
    def validate_llm_config(self) -> List[str]:
        """Validate LLM configuration with new simplified logic"""
        errors = []
        
        if not self.llm_model:
            errors.append(ERROR_MESSAGES["missing_model"])
            return errors
        
        try:
            # Infer provider from model string or use explicit provider
            if hasattr(self, 'llm_provider') and self.llm_provider:
                # Handle both string and enum values for backward compatibility
                if hasattr(self.llm_provider, 'value'):
                    provider = self.llm_provider.value
                else:
                    provider = str(self.llm_provider)
            else:
                provider = infer_provider_from_model(self.llm_model)
            
            # Check for API key (skip for local models like ollama)
            if provider != "ollama":
                api_key = get_api_key_for_provider(provider, self)
                if not api_key:
                    required_key = get_required_api_key_env_var(provider)
                    if required_key:  # Some providers might not need API keys
                        errors.append(ERROR_MESSAGES["missing_api_key"].format(
                            provider=provider, 
                            env_var=required_key
                        ))
        
        except ValueError as e:
            errors.append(str(e))
        
        return errors
    
    def validate_required_config(self) -> List[str]:
        """Validate required configuration values and return list of missing items"""
        missing = []
        
        # Validate LLM configuration
        llm_errors = self.validate_llm_config()
        missing.extend(llm_errors)
        
        # Check database configuration (only for PostgreSQL mode)
        if not self.is_sqlite:
            if not self.postgres_server:
                missing.append("POSTGRES_SERVER")
            if not self.postgres_user:
                missing.append("POSTGRES_USER")
            if not self.postgres_password:
                missing.append("POSTGRES_PASSWORD")
            if not self.postgres_db:
                missing.append("POSTGRES_DB")
            
        return missing


# Global settings instance
settings = KodiakSettings()


# Validate configuration on startup
def validate_startup_config():
    """Validate configuration on application startup"""
    from kodiak.core.error_handling import ErrorHandler, ConfigurationError
    
    try:
        missing_config = settings.validate_required_config()
        if missing_config:
            error_msg = (
                f"Missing required configuration values: {', '.join(missing_config)}. "
                f"Please set these environment variables or add them to your .env file. "
                f"See the documentation for configuration examples."
            )
            raise ConfigurationError(
                message=error_msg,
                details={
                    "missing_keys": missing_config,
                    "env_file_path": ".env",
                    "documentation_url": "https://docs.litellm.ai/docs/providers"
                }
            )
        
        # Additional LLM configuration validation
        try:
            # Test provider inference and API key resolution
            if hasattr(settings, 'llm_provider') and settings.llm_provider:
                if hasattr(settings.llm_provider, 'value'):
                    provider = settings.llm_provider.value
                else:
                    provider = str(settings.llm_provider)
            else:
                provider = infer_provider_from_model(settings.llm_model)
            
            # Log successful provider inference
            from loguru import logger
            logger.info(f"✅ LLM Provider inferred/configured: {provider}")
            logger.info(f"🧠 LLM Model: {settings.llm_model}")
            
        except ValueError as e:
            raise ConfigurationError(
                message=str(e),
                config_key="llm_model",
                details={
                    "model": settings.llm_model,
                    "suggestion": "Use format 'provider/model' or set KODIAK_LLM_PROVIDER explicitly"
                }
            )
        
        # Validate database configuration (only for PostgreSQL mode)
        if not settings.is_sqlite:
            try:
                db_url = settings.database_url
                if not all([settings.postgres_server, settings.postgres_user, settings.postgres_password, settings.postgres_db]):
                    raise ConfigurationError(
                        message="Incomplete database configuration. All database settings are required for PostgreSQL mode.",
                        config_key="database",
                        details={
                            "required_vars": ["POSTGRES_SERVER", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"],
                            "current_server": settings.postgres_server,
                            "current_db": settings.postgres_db
                        }
                    )
            except Exception as e:
                if not isinstance(e, ConfigurationError):
                    raise ConfigurationError(
                        message=f"Database configuration validation failed: {str(e)}",
                        config_key="database",
                        details={"database_url": settings.database_url}
                    )
                raise
        else:
            # SQLite mode - just log the path
            from loguru import logger
            logger.info(f"📦 Using SQLite database (zero-config mode)")
        
        # Log successful configuration
        from loguru import logger
        logger.info(f"✅ Configuration validation completed successfully")
        
        # Get provider info for logging
        try:
            if hasattr(settings, 'llm_provider') and settings.llm_provider:
                if hasattr(settings.llm_provider, 'value'):
                    provider = settings.llm_provider.value
                else:
                    provider = str(settings.llm_provider)
                provider_source = "explicit"
            else:
                provider = infer_provider_from_model(settings.llm_model)
                provider_source = "inferred"
            
            logger.info(f"🤖 LLM Provider: {provider} ({provider_source})")
        except Exception:
            logger.info(f"🤖 LLM Provider: unknown")
        
        logger.info(f"🧠 LLM Model: {settings.llm_model}")
        logger.info(f"🗄️  Database: {'SQLite' if settings.is_sqlite else 'PostgreSQL'} - {settings.database_url}")
        logger.info(f"🐛 Debug Mode: {settings.debug}")
        logger.info(f"🛡️  Safety Checks: {settings.enable_safety_checks}")
        logger.info(f"🐝 Hive Mind: {settings.enable_hive_mind}")
        logger.info(f"⚙️  Tool Timeout: {settings.tool_timeout}s")
        logger.info(f"🧠 Insight Memory: {'enabled' if settings.memory_enabled else 'disabled'}")
        logger.info(f"👥 Max Agents: {settings.max_concurrent_agents}")
        
        # Log configuration source information
        logger.info("📋 Configuration loaded from:")
        logger.info(f"   - Environment variables")
        logger.info(f"   - .env file (if present)")
        logger.info(f"   - Default values")
        
        # Provide helpful setup information
        if settings.debug:
            logger.info("🔧 Debug mode is enabled - detailed logging active")
        
        logger.info("🚀 System ready to start with validated configuration")
        
    except ConfigurationError:
        # Re-raise configuration errors as-is
        raise
    except Exception as e:
        # Wrap unexpected errors
        raise ConfigurationError(
            message=f"Unexpected error during configuration validation: {str(e)}",
            details={"error_type": type(e).__name__}
        )



# Global settings instance
settings = KodiakSettings()
