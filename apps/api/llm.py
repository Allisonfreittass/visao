import logging
from decimal import Decimal
from functools import lru_cache

from pydantic import SecretStr

from apps.api.settings import Settings, get_settings
from integrations.llm.base import LLMProvider, Pricing
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


def missing_fallback_settings(settings: Settings) -> list[str]:
    return _missing(
        "FALLBACK_",
        {
            "PROVIDER_NAME": settings.llm_fallback_provider_name,
            "BASE_URL": settings.llm_fallback_base_url,
            "API_KEY": settings.llm_fallback_api_key,
            "MODEL": settings.llm_fallback_model,
            "PRICE_INPUT_PER_MTOK": settings.llm_fallback_price_input_per_mtok,
            "PRICE_OUTPUT_PER_MTOK": settings.llm_fallback_price_output_per_mtok,
        },
    )


@lru_cache
def get_llm_provider() -> LLMProvider | None:
    return build_llm_provider(get_settings())


def _openai_compatible(
    settings: Settings,
    name: str | None,
    base_url: str | None,
    api_key: SecretStr | None,
    model: str | None,
    price_in: Decimal | None,
    price_out: Decimal | None,
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
    )


def build_llm_provider(settings: Settings) -> LLMProvider | None:
    """Returns None unless every primary setting, prices included, is present. A fully
    configured fallback is chained after the primary; a partial one is ignored with a warning."""
    if missing_llm_settings(settings):
        return None
    primary = _openai_compatible(
        settings,
        settings.llm_provider_name,
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        settings.llm_price_input_per_mtok,
        settings.llm_price_output_per_mtok,
    )
    missing = missing_fallback_settings(settings)
    if len(missing) == 6:
        return primary
    if missing:
        logger.warning(
            "LLM fallback ignored, missing: " + ", ".join(missing),
            extra={"event": "llm_fallback_incomplete"},
        )
        return primary
    fallback = _openai_compatible(
        settings,
        settings.llm_fallback_provider_name,
        settings.llm_fallback_base_url,
        settings.llm_fallback_api_key,
        settings.llm_fallback_model,
        settings.llm_fallback_price_input_per_mtok,
        settings.llm_fallback_price_output_per_mtok,
    )
    return FallbackLLMProvider([primary, fallback])
