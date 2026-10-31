from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-insecure-change-me"  # noqa: S105 (rejected in production)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VISION_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./dev.db"
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_ttl_minutes: int = Field(default=60, ge=1, le=24 * 60)
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> "Settings":
        if self.environment == "production" and (
            self.secret_key == DEFAULT_SECRET_KEY or len(self.secret_key) < 32
        ):
            raise ValueError("VISION_SECRET_KEY must be set (>= 32 chars) in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
