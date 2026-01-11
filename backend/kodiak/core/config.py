from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Kodiak"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = ["http://localhost:3000"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "kodiak"
    POSTGRES_PASSWORD: str = "kodiak"
    POSTGRES_DB: str = "kodiak_db"
    POSTGRES_PORT: str = "5432"
    DATABASE_URI: str | None = None

    @field_validator("DATABASE_URI", mode="before")
    def assemble_db_connection(cls, v: str | None, info) -> str:
        if isinstance(v, str):
            return v
        return (
            f"postgresql+psycopg://"
            f"{info.data.get('POSTGRES_USER')}:{info.data.get('POSTGRES_PASSWORD')}@"
            f"{info.data.get('POSTGRES_SERVER')}:{info.data.get('POSTGRES_PORT')}/"
            f"{info.data.get('POSTGRES_DB')}"
        )

    # LLM
    OPENAI_API_KEY: str | None = None
    KODIAK_MODEL: str = "gpt-4-turbo-preview"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

settings = Settings()
