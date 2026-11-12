import os
from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from integrations.llm.budget import FreeEndpointGrant

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
    database_schema: str | None = Field(default=None, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_ttl_minutes: int = Field(default=60, ge=1, le=24 * 60)
    log_level: str = "INFO"
    cloud_tick_key: SecretStr | None = Field(default=None, min_length=32)

    build_sha: str = "local"
    code_autonomy_enabled: bool = False
    code_autonomy_key: SecretStr | None = Field(default=None, min_length=32)

    # LLM: any OpenAI-compatible endpoint. Prices are mandatory: without them spending can't be
    # measured or capped, so the provider stays disabled.
    llm_provider_name: str | None = None
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_price_input_per_mtok: Decimal | None = Field(default=None, ge=0)
    llm_price_output_per_mtok: Decimal | None = Field(default=None, ge=0)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    # Explicit operator-reviewed grants; zero configured prices alone do not authorize I/O.
    llm_max_paid_spend_usd: Decimal = Field(default=Decimal(0), ge=0, le=0)
    # Paid providers (e.g. Claude): admitted only with both caps above zero, in USD, enforced by
    # the ledger before each call (integrations/llm/budget.py). Zero = only free providers.
    llm_paid_daily_usd: Decimal = Field(default=Decimal("0"), ge=0)
    llm_paid_monthly_usd: Decimal = Field(default=Decimal("0"), ge=0)
    llm_free_grants: list[FreeEndpointGrant] = Field(default_factory=list, max_length=32)
    llm_trust_zero_price: bool = False  # local use; a reported cost still freezes the ledger
    # Merged into conversation requests only, e.g. to turn the model's reasoning off.
    llm_fast_extra_body: dict[str, Any] = Field(default_factory=dict)
    llm_fallback_fast_extra_body: dict[str, Any] = Field(default_factory=dict)
    llm_fallback2_fast_extra_body: dict[str, Any] = Field(default_factory=dict)
    llm_budget_calls_per_day: int = Field(default=30, ge=1)
    llm_budget_calls_per_hour: int = Field(default=10, ge=1)
    llm_budget_input_tokens_per_day: int = Field(default=60_000, ge=1)
    llm_budget_output_tokens_per_day: int = Field(default=15_000, ge=1)
    # Measured in bytes: must fit llm_context_char_budget plus the system prompt, accents included.
    llm_budget_input_tokens_per_call: int = Field(default=80_000, ge=1)
    llm_budget_output_tokens_per_call: int = Field(default=4096, ge=1)
    llm_budget_concurrency: int = Field(default=1, ge=1)

    # Optional fallback provider, tried when the primary is out of quota, rate-limited or down.
    llm_fallback_provider_name: str | None = None
    llm_fallback_base_url: str | None = None
    llm_fallback_api_key: SecretStr | None = None
    llm_fallback_model: str | None = None
    llm_fallback_price_input_per_mtok: Decimal | None = Field(default=None, ge=0)
    llm_fallback_price_output_per_mtok: Decimal | None = Field(default=None, ge=0)
    # A second reserve, same shape: free tiers run out, so more than one is worth keeping.
    llm_fallback2_provider_name: str | None = None
    llm_fallback2_base_url: str | None = None
    llm_fallback2_api_key: SecretStr | None = None
    llm_fallback2_model: str | None = None
    llm_fallback2_price_input_per_mtok: Decimal | None = Field(default=None, ge=0)
    llm_fallback2_price_output_per_mtok: Decimal | None = Field(default=None, ge=0)
    # Room for a complete code answer; brevity comes from the prompt, not from cutting replies.
    llm_max_output_tokens: int = Field(default=2048, ge=1)
    # Curation asks for structured JSON; reasoning models think longer before answering it.
    llm_curation_max_output_tokens: int = Field(default=4096, ge=1)

    # Speech synthesis (docs/VOICE.md). Empty approved list = voice disabled. The list is the
    # human quality gate; which approved voice is the agent's own is the agent's decision.
    tts_models_dir: str = "models/tts"
    tts_approved_voices: str = ""
    tts_max_chars: int = Field(default=600, ge=10)
    # Speech recognition: faster-whisper size (tiny|base|small); empty = disabled.
    stt_model: str = ""
    stt_models_dir: str = "models/stt"
    # ~60 s of 16 kHz mono 16-bit WAV; longer turns are refused.
    stt_max_bytes: int = Field(default=2_000_000, ge=10_000)

    # Curiosity and research (docs/CURIOSITY.md). Off by default: one extra LLM call per
    # non-trivial turn, plus searches within the limits below.
    curiosity_enabled: bool = False
    research_per_day: int = Field(default=20, ge=0)
    research_per_conversation: int = Field(default=5, ge=0)
    research_max_results: int = Field(default=3, ge=1, le=10)

    # Autonomous cycle (docs/AUTONOMY.md): one scheduled job per window, plus a daily budget for
    # everything the agent does on its own. Zero calls = no autonomous model call at all.
    autonomy_cycle_minutes: int = Field(default=60, ge=5)
    # Inner life (docs/MIND.md): thinking between turns, interest-led study, starting conversations.
    mind_enabled: bool = False
    mind_think_minutes: int = Field(default=20, ge=5)
    mind_review_turns: int = Field(default=4, ge=1)
    mind_initiatives_per_day: int = Field(default=6, ge=0)
    study_interval_minutes: int = Field(default=360, ge=10)
    # Web Push (docs/MIND.md): lets an opening reach the phone with the app closed. Off unless all
    # three are set; generate the pair with `python -m apps.api.cli webpush-keys`.
    webpush_public_key: str | None = None
    webpush_private_key: SecretStr | None = None
    webpush_subject: str | None = None  # https URL of the app or mailto: contact (VAPID "sub")
    autonomy_llm_calls_per_day: int = Field(default=20, ge=0)
    autonomy_tokens_per_day: int = Field(default=60_000, ge=0)
    autonomy_max_actions_per_cycle: int = Field(default=3, ge=0)
    autonomy_max_seconds: float = Field(default=120.0, gt=0)

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
        "llm_fallback_provider_name",
        "llm_fallback_base_url",
        "llm_fallback_api_key",
        "llm_fallback_model",
        "llm_fallback_price_input_per_mtok",
        "llm_fallback_price_output_per_mtok",
        "llm_fallback2_provider_name",
        "llm_fallback2_base_url",
        "llm_fallback2_api_key",
        "llm_fallback2_model",
        "llm_fallback2_price_input_per_mtok",
        "llm_fallback2_price_output_per_mtok",
        "webpush_public_key",
        "webpush_private_key",
        "webpush_subject",
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
