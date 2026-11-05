import logging
from decimal import Decimal
from functools import lru_cache

from pydantic import SecretStr

from apps.api.settings import Settings, get_settings
from integrations.llm.base import LLMProvider, Pricing
from integrations.llm.budget import BudgetGuard, BudgetLimits, GuardedLLMProvider
from integrations.llm.fallback import FallbackLLMProvider
from integrations.llm.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


def _missing(prefix: str, values: dict[str, object]) -> list[str]:
    return [f"VISION_LLM_{prefix}{name}" for name, value in values.items() if value in (None, "")]


def missing_llm_settings(settings: Settings) -> list[str]:
    return _missing(
        "",
        {
            "PROVIDER_NAME": settings.llm_provider_name,
            "BASE_URL": settings.llm_base_url,
            "API_KEY": settings.llm_api_key,
            "MODEL": settings.llm_model,
            "PRICE_INPUT_PER_MTOK": settings.llm_price_input_per_mtok,
            "PRICE_OUTPUT_PER_MTOK": settings.llm_price_output_per_mtok,
        },
    )


def missing_fallback_settings(settings: Settings, slot: str = "fallback") -> list[str]:
    return _missing(
        f"{slot.upper()}_",
        {
            name: getattr(settings, f"llm_{slot}_{name.lower()}")
            for name in (
                "PROVIDER_NAME",
                "BASE_URL",
                "API_KEY",
                "MODEL",
                "PRICE_INPUT_PER_MTOK",
                "PRICE_OUTPUT_PER_MTOK",
            )
        },
    )


@lru_cache
def get_llm_provider() -> LLMProvider | None:
    # Conversation favours speed; background thinking keeps the model's full reasoning.
    return build_llm_provider(get_settings(), fast=True)


def _openai_compatible(
    settings: Settings,
    name: str | None,
    base_url: str | None,
    api_key: SecretStr | None,
    model: str | None,
    price_in: Decimal | None,
    price_out: Decimal | None,
    extra_body: dict | None = None,
) -> OpenAICompatibleProvider:
    assert name and base_url and api_key and model
    assert price_in is not None and price_out is not None
    return OpenAICompatibleProvider(
        name=name,
        base_url=base_url,
        api_key=api_key.get_secret_value(),
        model=model,
        pricing=Pricing(input_per_mtok=price_in, output_per_mtok=price_out),
        timeout_seconds=settings.llm_timeout_seconds,
        # Each transport attempt needs its own reservation; fallback handles retry admission.
        max_retries=0,
        extra_body=extra_body,
    )


def build_llm_provider(
    settings: Settings, *, budget_guard: BudgetGuard | None = None, fast: bool = False
) -> LLMProvider | None:
    """Returns None unless every primary setting, prices included, is present. A fully
    configured fallback is chained after the primary; a partial one is ignored with a warning."""
    if missing_llm_settings(settings):
        return None
    if budget_guard is None:
        from infrastructure.database.session import get_sessionmaker

        budget_guard = BudgetGuard(
            lambda: get_sessionmaker()(),
            settings.llm_free_grants,
            BudgetLimits(
                calls_per_day=settings.llm_budget_calls_per_day,
                calls_per_hour=settings.llm_budget_calls_per_hour,
                input_tokens_per_day=settings.llm_budget_input_tokens_per_day,
                output_tokens_per_day=settings.llm_budget_output_tokens_per_day,
                input_tokens_per_call=settings.llm_budget_input_tokens_per_call,
                output_tokens_per_call=settings.llm_budget_output_tokens_per_call,
                concurrency=settings.llm_budget_concurrency,
            ),
            trust_zero_price=settings.llm_trust_zero_price,
        )
    primary_raw = _openai_compatible(
        settings,
        settings.llm_provider_name,
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        settings.llm_price_input_per_mtok,
        settings.llm_price_output_per_mtok,
        settings.llm_fast_extra_body if fast else None,
    )
    primary = GuardedLLMProvider(primary_raw, settings.llm_base_url, budget_guard)
    missing = missing_fallback_settings(settings)
    if len(missing) == 6:
        return primary
    if missing:
        logger.warning(
            "LLM fallback ignored, missing: " + ", ".join(missing),
            extra={"event": "llm_fallback_incomplete"},
        )
        return primary
    fallback_raw = _openai_compatible(
        settings,
        settings.llm_fallback_provider_name,
        settings.llm_fallback_base_url,
        settings.llm_fallback_api_key,
        settings.llm_fallback_model,
        settings.llm_fallback_price_input_per_mtok,
        settings.llm_fallback_price_output_per_mtok,
        settings.llm_fallback_fast_extra_body if fast else None,
    )
    chain = [
        primary,
        GuardedLLMProvider(fallback_raw, settings.llm_fallback_base_url, budget_guard),
    ]
    missing = missing_fallback_settings(settings, "fallback2")
    if missing and len(missing) < 6:
        logger.warning(
            "second LLM fallback ignored, missing: " + ", ".join(missing),
            extra={"event": "llm_fallback_incomplete"},
        )
    elif not missing:
        second = _openai_compatible(
            settings,
            settings.llm_fallback2_provider_name,
            settings.llm_fallback2_base_url,
            settings.llm_fallback2_api_key,
            settings.llm_fallback2_model,
            settings.llm_fallback2_price_input_per_mtok,
            settings.llm_fallback2_price_output_per_mtok,
        )
        chain.append(GuardedLLMProvider(second, settings.llm_fallback2_base_url, budget_guard))
    return FallbackLLMProvider(chain)
