"""
Configuration management for Kodiak (Gemini-only).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from kodiak.services import llm


ERROR_MESSAGES = {
    "missing_model": (
        "KODIAK_LLM_MODEL is required. "
        "Supported: gemini/gemini-3.1-pro-preview, gemini/gemini-3-flash-preview"
    ),
    "missing_api_key": "GOOGLE_API_KEY is required for Gemini.",
    "invalid_thinking_level": (
        "KODIAK_GEMINI_THINKING_LEVEL must be one of: low, medium, high. "
        "Flash also supports: minimal."
    ),
}


class KodiakSettings(BaseSettings):
    """Kodiak application settings."""

    # Application
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

    # LLM (Gemini only)
    llm_model: str = Field(default="gemini/gemini-3.1-pro-preview", alias="KODIAK_LLM_MODEL")
    llm_api_key: Optional[str] = Field(default=None, alias="KODIAK_LLM_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    llm_temperature: float = Field(default=1.0, alias="KODIAK_LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=8192, alias="KODIAK_LLM_MAX_TOKENS")  # Output can be large containing arrays of JSON actions
    llm_knowledge_cutoff: str = Field(default="2025-01", alias="KODIAK_LLM_KNOWLEDGE_CUTOFF")
    gemini_thinking_level: str = Field(default="high", alias="KODIAK_GEMINI_THINKING_LEVEL")
    max_tools_in_prompt: int = Field(default=16, alias="KODIAK_MAX_TOOLS_IN_PROMPT")

    # Multi-agent pipeline
    multi_agent: bool = Field(default=True, alias="KODIAK_MULTI_AGENT")
    multi_agent_workers: int = Field(default=4, alias="KODIAK_MULTI_AGENT_WORKERS")
    multi_agent_max_duration: int = Field(default=3600, alias="KODIAK_MULTI_AGENT_MAX_DURATION")

    # Planner agent settings
    planner_model: str = Field(default="gemini/gemini-3-flash-preview", alias="KODIAK_PLANNER_MODEL")
    planner_cycle_interval: float = Field(default=8.0, alias="KODIAK_PLANNER_CYCLE_INTERVAL")
    planner_max_cycles: int = Field(default=200, alias="KODIAK_PLANNER_MAX_CYCLES")

    # Analyst agent settings
    analyst_model: str = Field(default="gemini/gemini-3.1-pro-preview", alias="KODIAK_ANALYST_MODEL")
    analyst_poll_interval: float = Field(default=15.0, alias="KODIAK_ANALYST_POLL_INTERVAL")
    analyst_max_cycles: int = Field(default=100, alias="KODIAK_ANALYST_MAX_CYCLES")
    analyst_settle_cycles: int = Field(default=2, alias="KODIAK_ANALYST_SETTLE_CYCLES")
    analyst_min_results_per_batch: int = Field(default=1, alias="KODIAK_ANALYST_MIN_RESULTS")

    # Failure handling
    failure_threshold: int = Field(default=3, alias="KODIAK_FAILURE_THRESHOLD")

    # Security/runtime
    enable_safety_checks: bool = Field(default=True, alias="KODIAK_ENABLE_SAFETY")
    tool_timeout: int = Field(default=300, alias="KODIAK_TOOL_TIMEOUT")
    global_tool_concurrency: int = Field(default=6, alias="KODIAK_GLOBAL_CONCURRENCY")
    heavy_tool_parallel_limit: int = Field(default=2, alias="KODIAK_HEAVY_TOOL_PARALLEL_LIMIT")
    tool_scheduler: str = Field(default="queue", alias="KODIAK_TOOL_SCHEDULER")
    tool_queue_limit: int = Field(default=50, alias="KODIAK_TOOL_QUEUE_LIMIT")
    report_output_path: str = Field(default=str(Path.home() / ".kodiak" / "reports"), alias="KODIAK_REPORT_PATH")
    toolbox_image: str = Field(default="ghcr.io/keethesh/kodiak-toolbox:latest", alias="KODIAK_TOOLBOX_IMAGE")
    docker_memory_limit: str = Field(default="2g", alias="KODIAK_DOCKER_MEMORY")
    docker_cpu_limit: float = Field(default=2.0, alias="KODIAK_DOCKER_CPUS")

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

    def get_model_display_name(self) -> str:
        model = llm.normalize_model_name(self.llm_model)
        if model.endswith("gemini-3.1-pro-preview"):
            return "Gemini 3.1 Pro"
        if model.endswith("gemini-3-flash-preview"):
            return "Gemini 3 Flash"
        return model

    def get_model_info(self) -> Dict[str, Any]:
        try:
            normalized = llm.normalize_model_name(self.llm_model)
            return {
                "model": normalized,
                "provider": "gemini",
                "provider_source": "fixed",
                "api_key_configured": bool(self.google_api_key or self.llm_api_key),
                "temperature": self.llm_temperature,
                "max_tokens": self.llm_max_tokens,
                "gemini_thinking_level": llm.normalize_gemini_thinking_level(self.gemini_thinking_level),
                "max_tools_in_prompt": self.max_tools_in_prompt,
            }
        except Exception as e:
            return {"model": self.llm_model, "error": str(e), "api_key_configured": False}

    def get_llm_config(self) -> Dict[str, Any]:
        model = llm.normalize_model_name(self.llm_model)
        return {
            "model": model,
            "api_key": llm.get_google_api_key(),
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
            "thinking_level": llm.resolve_gemini_thinking_level(model, self.gemini_thinking_level),
        }

    def get_planner_model(self) -> str:
        """Get the model for the Planner agent (typically Flash for speed)."""
        return llm.normalize_model_name(self.planner_model)

    def get_analyst_model(self) -> str:
        """Get the model for the Analyst agent (typically Pro for depth)."""
        return llm.normalize_model_name(self.analyst_model)

    def get_agent_models(self) -> Dict[str, str]:
        """Get both agent models normalized."""
        return {
            "planner": self.get_planner_model(),
            "analyst": self.get_analyst_model(),
        }

    def validate_llm_config(self) -> List[str]:
        errors: List[str] = []
        if not self.llm_model:
            errors.append(ERROR_MESSAGES["missing_model"])
            return errors

        try:
            llm.normalize_model_name(self.llm_model)
        except ValueError as e:
            errors.append(str(e))

        if not (self.google_api_key or self.llm_api_key):
            errors.append(ERROR_MESSAGES["missing_api_key"])

        if llm.normalize_gemini_thinking_level(self.gemini_thinking_level) != str(self.gemini_thinking_level).strip().lower():
            errors.append(ERROR_MESSAGES["invalid_thinking_level"])

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
                + ". Configure Gemini with `kodiak config`."
            ),
            details={"missing_keys": missing, "documentation_url": "https://ai.google.dev/gemini-api/docs/gemini-3"},
        )

    normalized_model = llm.normalize_model_name(settings.llm_model)
    logger.info("✅ Configuration validation completed successfully")
    logger.info("🤖 LLM Provider: gemini (fixed)")
    logger.info(f"🧠 LLM Model: {normalized_model}")
    logger.info(f"🗄️  Database: {'SQLite' if settings.is_sqlite else 'PostgreSQL'} - {settings.database_url}")
    logger.info(f"🐛 Debug Mode: {settings.debug}")
    logger.info(f"🛡️  Safety Checks: {settings.enable_safety_checks}")
    logger.info(f"🤖 Runtime: multi-agent kernel ({settings.multi_agent_workers} workers)")
    logger.info(f"⚙️  Tool Timeout: {settings.tool_timeout}s")
    logger.info(f"🔧 Global Tool Concurrency: {settings.global_tool_concurrency}")
    logger.info(f"🧰 Heavy Tool Parallel Limit: {settings.heavy_tool_parallel_limit}")
