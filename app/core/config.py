from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    catalog_path: Path = Field(
        default=PROJECT_ROOT / "data/processed/shl_catalog.sample.json",
        alias="CATALOG_PATH",
    )
    max_recommendations: int = Field(default=5, alias="MAX_RECOMMENDATIONS")
    min_context_signals: int = Field(default=2, alias="MIN_CONTEXT_SIGNALS")
    shl_agent_model: str = Field(default="", alias="SHL_AGENT_MODEL")
    shl_agent_base_url: str = Field(default="", alias="SHL_AGENT_BASE_URL")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
