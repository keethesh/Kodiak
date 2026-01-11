"""
Configuration management for Kodiak

Supports multiple LLM providers including OpenAI, Gemini, Claude, and others
through LiteLLM with flexible environment-based configuration.
"""

import os
from typing import Optional, Dict, Any, List
from pydantic_settings import BaseSettings
from pydantic import Field
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
    
    # Application Configuration
    PROJECT_NAME: str = Field(default="Kodiak", env="KODIAK_PROJECT_NAME")
    VERSION: str = Field(default="1.0.0", env="KODIAK_VERSION")
    
    # TUI Configuration
    tui_color_theme: str = Field(default="dark", env="KODIAK_TUI_COLOR_THEME")
    tui_refresh_rate: int = Field(default=10, env="KODIAK_TUI_REFRESH_RATE")  # Hz
    
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
    
    def validate_required_config(self) -> List[str]:
        """Validate required configuration values and return list of missing items"""
        missing = []
        
        # Check for required API keys based on provider
        if self.llm_provider == LLMProvider.OPENAI and not self.openai_api_key and not self.llm_api_key:
            missing.append("OPENAI_API_KEY or KODIAK_LLM_API_KEY")
        elif self.llm_provider == LLMProvider.GEMINI and not self.google_api_key and not self.llm_api_key:
            missing.append("GOOGLE_API_KEY or KODIAK_LLM_API_KEY")
        elif self.llm_provider == LLMProvider.CLAUDE and not self.anthropic_api_key and not self.llm_api_key:
            missing.append("ANTHROPIC_API_KEY or KODIAK_LLM_API_KEY")
        
        # Check database configuration
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
                    "documentation_url": "https://github.com/your-org/kodiak/docs/configuration.md"
                }
            )
        
        # Validate LLM configuration
        try:
            llm_config = settings.get_llm_config()
            if not llm_config.get("api_key"):
                provider_key_map = {
                    "gemini": "GOOGLE_API_KEY",
                    "openai": "OPENAI_API_KEY", 
                    "claude": "ANTHROPIC_API_KEY"
                }
                suggested_key = provider_key_map.get(settings.llm_provider, "KODIAK_LLM_API_KEY")
                raise ConfigurationError(
                    message=f"No API key found for LLM provider '{settings.llm_provider}'. Please set {suggested_key}.",
                    config_key=suggested_key,
                    details={
                        "provider": settings.llm_provider,
                        "model": settings.llm_model,
                        "suggested_env_var": suggested_key
                    }
                )
        except Exception as e:
            if not isinstance(e, ConfigurationError):
                raise ConfigurationError(
                    message=f"LLM configuration validation failed: {str(e)}",
                    config_key="llm_config",
                    details={"provider": settings.llm_provider, "model": settings.llm_model}
                )
            raise
        
        # Validate database configuration
        try:
            db_url = settings.database_url
            if not all([settings.postgres_server, settings.postgres_user, settings.postgres_password, settings.postgres_db]):
                raise ConfigurationError(
                    message="Incomplete database configuration. All database settings are required.",
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
        
        # Log successful configuration
        from loguru import logger
        logger.info(f"✅ Configuration validation completed successfully")
        logger.info(f"🤖 LLM Provider: {settings.llm_provider}")
        logger.info(f"🧠 LLM Model: {settings.get_model_display_name()}")
        logger.info(f"🗄️  Database: {settings.postgres_server}:{settings.postgres_port}/{settings.postgres_db}")
        logger.info(f"🐛 Debug Mode: {settings.debug}")
        logger.info(f"🛡️  Safety Checks: {settings.enable_safety_checks}")
        logger.info(f"🐝 Hive Mind: {settings.enable_hive_mind}")
        logger.info(f"⚙️  Tool Timeout: {settings.tool_timeout}s")
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


def get_configuration_troubleshooting_guide() -> Dict[str, Any]:
    """Get troubleshooting guide for common configuration issues"""
    return {
        "common_issues": {
            "missing_api_key": {
                "symptoms": ["ConfigurationError about missing API key", "LLM provider not configured"],
                "solutions": [
                    "Set the appropriate API key environment variable:",
                    "  - For Gemini: GOOGLE_API_KEY=your_key",
                    "  - For OpenAI: OPENAI_API_KEY=your_key", 
                    "  - For Claude: ANTHROPIC_API_KEY=your_key",
                    "  - Or use generic: KODIAK_LLM_API_KEY=your_key",
                    "Create a .env file in the backend directory with your keys"
                ]
            },
            "database_connection": {
                "symptoms": ["Database connection failed", "PostgreSQL connection error"],
                "solutions": [
                    "Ensure PostgreSQL is running",
                    "Check database configuration:",
                    "  - POSTGRES_SERVER=localhost (or your server)",
                    "  - POSTGRES_PORT=5432 (or your port)",
                    "  - POSTGRES_USER=kodiak (or your user)",
                    "  - POSTGRES_PASSWORD=your_password",
                    "  - POSTGRES_DB=kodiak_db (or your database)",
                    "Run: docker-compose up db (if using Docker)"
                ]
            },
            "invalid_model": {
                "symptoms": ["Model not found", "Invalid model configuration"],
                "solutions": [
                    "Use supported model formats:",
                    "  - Gemini: gemini/gemini-1.5-pro",
                    "  - OpenAI: openai/gpt-4",
                    "  - Claude: claude-3-5-sonnet-20241022",
                    "Check available models with get_available_models()"
                ]
            }
        },
        "configuration_examples": {
            "gemini": {
                "KODIAK_LLM_PROVIDER": "gemini",
                "KODIAK_LLM_MODEL": "gemini/gemini-1.5-pro",
                "GOOGLE_API_KEY": "your_google_api_key_here"
            },
            "openai": {
                "KODIAK_LLM_PROVIDER": "openai", 
                "KODIAK_LLM_MODEL": "openai/gpt-4",
                "OPENAI_API_KEY": "your_openai_api_key_here"
            },
            "claude": {
                "KODIAK_LLM_PROVIDER": "claude",
                "KODIAK_LLM_MODEL": "claude-3-5-sonnet-20241022", 
                "ANTHROPIC_API_KEY": "your_anthropic_api_key_here"
            }
        },
        "setup_commands": [
            "# 1. Copy example environment file",
            "cp .env.example .env",
            "",
            "# 2. Edit .env file with your API keys",
            "nano .env  # or your preferred editor",
            "",
            "# 3. Start database (if using Docker)",
            "docker-compose up -d db",
            "",
            "# 4. Run configuration helper",
            "python configure_llm.py",
            "",
            "# 5. Start the application",
            "python main.py"
        ]
    }


def diagnose_configuration_issues() -> Dict[str, Any]:
    """Diagnose common configuration issues and provide solutions"""
    issues = []
    solutions = []
    
    try:
        # Check LLM configuration
        llm_config = settings.get_llm_config()
        if not llm_config.get("api_key"):
            issues.append(f"Missing API key for LLM provider: {settings.llm_provider}")
            
            provider_solutions = {
                "gemini": "Set GOOGLE_API_KEY environment variable",
                "openai": "Set OPENAI_API_KEY environment variable", 
                "claude": "Set ANTHROPIC_API_KEY environment variable"
            }
            
            solution = provider_solutions.get(settings.llm_provider, "Set KODIAK_LLM_API_KEY environment variable")
            solutions.append(solution)
    
    except Exception as e:
        issues.append(f"LLM configuration error: {str(e)}")
        solutions.append("Check LLM provider and model configuration")
    
    # Check database configuration
    missing_db_config = []
    if not settings.postgres_server:
        missing_db_config.append("POSTGRES_SERVER")
    if not settings.postgres_user:
        missing_db_config.append("POSTGRES_USER")
    if not settings.postgres_password:
        missing_db_config.append("POSTGRES_PASSWORD")
    if not settings.postgres_db:
        missing_db_config.append("POSTGRES_DB")
    
    if missing_db_config:
        issues.append(f"Missing database configuration: {', '.join(missing_db_config)}")
        solutions.append("Set all required database environment variables")
    
    # Check for common misconfigurations
    if settings.llm_model and not settings.llm_model.startswith(settings.llm_provider):
        issues.append(f"Model '{settings.llm_model}' may not match provider '{settings.llm_provider}'")
        solutions.append("Ensure model format matches provider (e.g., 'gemini/gemini-1.5-pro' for Gemini)")
    
    return {
        "has_issues": len(issues) > 0,
        "issues": issues,
        "solutions": solutions,
        "troubleshooting_guide": get_configuration_troubleshooting_guide()
    }


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