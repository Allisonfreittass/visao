import os
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-insecure-change-me"  # noqa: S105 (rejected in production)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VISION_",
        # Tests point this at an empty file so a developer's real .env never leaks in.
        env_file=os.environ.get("VISION_ENV_FILE", ".env"),
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./dev.db"
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_ttl_minutes: int = Field(default=60, ge=1, le=24 * 60)
    log_level: str = "INFO"

    # LLM: any OpenAI-compatible endpoint. Prices are mandatory: without them spending can't be
    # measured or capped, so the provider stays disabled.
    llm_provider_name: str | None = None
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_price_input_per_mtok: Decimal | None = Field(default=None, ge=0)
    llm_price_output_per_mtok: Decimal | None = Field(default=None, ge=0)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_output_tokens: int = Field(default=1024, ge=1)

    # Budgets in USD (docs/COSTS.md). Enforced in code before every call.
    llm_daily_budget_usd: Decimal = Field(default=Decimal("1.50"), ge=0)
    llm_conversation_budget_usd: Decimal = Field(default=Decimal("0.30"), ge=0)
    # Rough cap on conversation history sent per call, in characters.
    llm_context_char_budget: int = Field(default=24_000, ge=1000)

    @field_validator(
        "llm_provider_name",
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "llm_price_input_per_mtok",
        "llm_price_output_per_mtok",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        # Docker Compose passes unset variables as "", which must mean "not configured".
        return None if isinstance(value, str) and not value.strip() else value

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
