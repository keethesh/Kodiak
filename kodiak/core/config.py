"""
Configuration management for Kodiak (OpenRouter via LiteLLM).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ERROR_MESSAGES = {
    "missing_model": (
        "KODIAK_LLM_MODEL is required. "
        "Supported: anthropic/claude-3.5-sonnet, openai/gpt-4o, etc. (via OpenRouter)"
    ),
    "missing_api_key": "KODIAK_OPENROUTER_API_KEY is required for OpenRouter.",
    "invalid_provider": "KODIAK_LLM_PROVIDER must be omitted or set to 'openrouter'.",
}


SUPPORTED_PROVIDERS = ["openrouter"]

SUPPORTED_MODELS = {
    "openrouter": [
        "anthropic/claude-3.5-sonnet-20241022",
        "anthropic/claude-3.5-haiku-20241022",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "x-ai/grok-2",
        "meta-llama/llama-3.1-70b-instruct",
        "google/gemini-2.0-flash-exp",
    ],
}


class KodiakSettings(BaseSettings):
    """Kodiak application settings."""

    PROJECT_NAME: str = Field(default="Kodiak", alias="KODIAK_PROJECT_NAME")
    VERSION: str = Field(default="1.0.0", alias="KODIAK_VERSION")
    debug: bool = Field(default=False, alias="KODIAK_DEBUG")
    log_level: str = Field(default="INFO", alias="KODIAK_LOG_LEVEL")

    # TUI
    tui_color_theme: str = Field(default="dark", alias="KODIAK_TUI_COLOR_THEME")
    tui_refresh_rate: int = Field(default=10, alias="KODIAK_TUI_REFRESH_RATE")

    # Database
    db_type: str = Field(default="sqlite", alias="KODIAK_DB_TYPE")
    sqlite_path: Optional[str] = Field(default=None, alias="KODIAK_SQLITE_PATH")
    postgres_server: str = Field(default="localhost", alias="POSTGRES_SERVER")
    postgres_user: str = Field(default="kodiak", alias="POSTGRES_USER")
    postgres_password: str = Field(default="kodiak_password", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="kodiak_db", alias="POSTGRES_DB")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    # LLM Provider (OpenRouter via LiteLLM)
    llm_provider: str = Field(default="openrouter", alias="KODIAK_LLM_PROVIDER")
    openrouter_api_key: Optional[str] = Field(default=None, alias="KODIAK_OPENROUTER_API_KEY")
    openrouter_base_url: Optional[str] = Field(default=None, alias="KODIAK_OPENROUTER_BASE_URL")
    llm_temperature: float = Field(default=1.0, alias="KODIAK_LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=8192, alias="KODIAK_LLM_MAX_TOKENS")
    llm_model: str = Field(default="anthropic/claude-3.5-sonnet-20241022", alias="KODIAK_LLM_MODEL")
    max_tools_in_prompt: int = Field(default=16, alias="KODIAK_MAX_TOOLS_IN_PROMPT")

    # Multi-agent pipeline
    multi_agent: bool = Field(default=True, alias="KODIAK_MULTI_AGENT")
    multi_agent_workers: int = Field(default=4, alias="KODIAK_MULTI_AGENT_WORKERS")
    multi_agent_max_duration: int = Field(default=3600, alias="KODIAK_MULTI_AGENT_MAX_DURATION")

    # Planner agent settings
    planner_model: str = Field(
        default="anthropic/claude-3.5-haiku-20241022",
        alias="KODIAK_PLANNER_MODEL"
    )
    planner_cycle_interval: float = Field(default=8.0, alias="KODIAK_PLANNER_CYCLE_INTERVAL")
    planner_max_cycles: int = Field(default=200, alias="KODIAK_PLANNER_MAX_CYCLES")

    # Analyst agent settings
    analyst_model: str = Field(
        default="anthropic/claude-3.5-sonnet-20241022",
        alias="KODIAK_ANALYST_MODEL"
    )
    analyst_poll_interval: float = Field(default=15.0, alias="KODIAK_ANALYST_POLL_INTERVAL")
    analyst_max_cycles: int = Field(default=100, alias="KODIAK_ANALYST_MAX_CYCLES")
    analyst_settle_cycles: int = Field(default=2, alias="KODIAK_ANALYST_SETTLE_CYCLES")
    analyst_min_results_per_batch: int = Field(default=1, alias="KODIAK_ANALYST_MIN_RESULTS")

    # Failure handling
    failure_threshold: int = Field(default=3, alias="KODIAK_FAILURE_THRESHOLD")

    # Tool classification
    HEAVY_TOOLS: frozenset = Field(
        default=frozenset({
            "nuclei", "ffuf", "katana", "gau", "sqlmap",
            "nmap", "commix", "wpscan", "hydra", "nikto",
        }),
    )

    # Security/runtime
    enable_safety_checks: bool = Field(default=True, alias="KODIAK_ENABLE_SAFETY")
    tool_timeout: int = Field(default=300, alias="KODIAK_TOOL_TIMEOUT")
    global_tool_concurrency: int = Field(default=6, alias="KODIAK_GLOBAL_CONCURRENCY")
    heavy_tool_parallel_limit: int = Field(default=2, alias="KODIAK_HEAVY_TOOL_PARALLEL_LIMIT")
    tool_scheduler: str = Field(default="queue", alias="KODIAK_TOOL_SCHEDULER")
    tool_queue_limit: int = Field(default=50, alias="KODIAK_TOOL_QUEUE_LIMIT")
    report_output_path: str = Field(
        default=str(Path.home() / ".kodiak" / "reports"),
        alias="KODIAK_REPORT_PATH"
    )
    toolbox_image: str = Field(
        default="ghcr.io/keethesh/kodiak-toolbox:latest",
        alias="KODIAK_TOOLBOX_IMAGE"
    )
    docker_memory_limit: str = Field(default="2g", alias="KODIAK_DOCKER_MEMORY")
    docker_cpu_limit: float = Field(default=2.0, alias="KODIAK_DOCKER_CPUS")
    docker_network_mode: Optional[str] = Field(default=None, alias="KODIAK_DOCKER_NETWORK")

    model_config = SettingsConfigDict(
        env_file=[
            ".env",
            str(Path.home() / ".kodiak" / "config.env"),
        ],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def _get_default_sqlite_path(self) -> str:
        kodiak_dir = Path.home() / ".kodiak"
        kodiak_dir.mkdir(exist_ok=True)
        return str(kodiak_dir / "kodiak.db")

    @property
    def database_url(self) -> str:
        if self.db_type.lower() == "sqlite":
            db_path = self.sqlite_path or self._get_default_sqlite_path()
            return f"sqlite:///{db_path}"
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        if self.db_type.lower() == "sqlite":
            db_path = self.sqlite_path or self._get_default_sqlite_path()
            return f"sqlite+aiosqlite:///{db_path}"
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_sqlite(self) -> bool:
        return self.db_type.lower() == "sqlite"

    def get_resolved_api_key(self) -> str:
        """Resolve API key from settings/env."""
        return (
            self.openrouter_api_key
            or os.getenv("KODIAK_OPENROUTER_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or ""
        )

    def get_model_display_name(self) -> str:
        """Get a human-readable model name."""
        model = self.llm_model
        if "claude" in model.lower():
            return "Claude 3.5 Sonnet"
        if "gpt-4o" in model.lower():
            return "GPT-4o"
        if "gemini" in model.lower():
            return "Gemini"
        if "grok" in model.lower():
            return "Grok 2"
        if "llama" in model.lower():
            return "Llama 3.1"
        return model

    def get_model_info(self) -> Dict[str, Any]:
        """Get model information for display."""
        return {
            "provider": self.llm_provider,
            "model": self.llm_model,
            "api_key_configured": bool(self.get_resolved_api_key()),
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
            "max_tools_in_prompt": self.max_tools_in_prompt,
        }

    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration for LiteLLM client."""
        return {
            "provider": self.llm_provider,
            "model": self.llm_model,
            "api_key": self.get_resolved_api_key(),
            "base_url": self.openrouter_base_url,
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
        }

    def get_planner_model(self) -> str:
        """Get the model for the Planner agent."""
        return self.planner_model

    def get_analyst_model(self) -> str:
        """Get the model for the Analyst agent."""
        return self.analyst_model

    def get_agent_models(self) -> Dict[str, str]:
        """Get both agent models."""
        return {
            "planner": self.get_planner_model(),
            "analyst": self.get_analyst_model(),
        }

    def validate_llm_config(self) -> List[str]:
        errors: List[str] = []

        if self.llm_provider not in SUPPORTED_PROVIDERS:
            errors.append(ERROR_MESSAGES["invalid_provider"])

        if not self.llm_model:
            errors.append(ERROR_MESSAGES["missing_model"])

        if not self.get_resolved_api_key():
            errors.append(ERROR_MESSAGES["missing_api_key"])

        return errors

    def validate_required_config(self) -> List[str]:
        missing: List[str] = []
        missing.extend(self.validate_llm_config())
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


settings = KodiakSettings()


def validate_startup_config() -> None:
    from kodiak.core.error_handling import ConfigurationError

    missing = settings.validate_required_config()
    if missing:
        raise ConfigurationError(
            message=(
                "Missing required configuration values: "
                + ", ".join(missing)
                + ". Configure with `kodiak config`."
            ),
            details={
                "missing_keys": missing,
                "documentation_url": "https://openrouter.ai/docs",
            },
        )

    logger.info("✅ Configuration validation completed successfully")
    logger.info(f"🤖 LLM Provider: {settings.llm_provider} (via LiteLLM)")
    logger.info(f"🧠 LLM Model: {settings.llm_model}")
    logger.info(f"📊 Database: {'SQLite' if settings.is_sqlite else 'PostgreSQL'}")
    logger.info(f"🐛 Debug Mode: {settings.debug}")
    logger.info(f"🛡️  Safety Checks: {settings.enable_safety_checks}")
    logger.info(f"🤖 Runtime: multi-agent kernel ({settings.multi_agent_workers} workers)")
    logger.info(f"⚙️  Tool Timeout: {settings.tool_timeout}s")
    logger.info(f"🔧 Global Tool Concurrency: {settings.global_tool_concurrency}")
    logger.info(f"🧰 Heavy Tool Parallel Limit: {settings.heavy_tool_parallel_limit}")
