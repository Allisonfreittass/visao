from functools import lru_cache

from apps.api.settings import Settings, get_settings
from integrations.llm.base import LLMProvider, Pricing
from integrations.llm.openai_compatible import OpenAICompatibleProvider


def missing_llm_settings(settings: Settings) -> list[str]:
    required = {
        "VISION_LLM_PROVIDER_NAME": settings.llm_provider_name,
        "VISION_LLM_BASE_URL": settings.llm_base_url,
        "VISION_LLM_API_KEY": settings.llm_api_key,
        "VISION_LLM_MODEL": settings.llm_model,
        "VISION_LLM_PRICE_INPUT_PER_MTOK": settings.llm_price_input_per_mtok,
        "VISION_LLM_PRICE_OUTPUT_PER_MTOK": settings.llm_price_output_per_mtok,
    }
    return [name for name, value in required.items() if value in (None, "")]


@lru_cache
def get_llm_provider() -> LLMProvider | None:
    return build_llm_provider(get_settings())


def build_llm_provider(settings: Settings) -> LLMProvider | None:
    """Returns None unless every setting, prices included, is present."""
    if missing_llm_settings(settings):
        return None
    assert settings.llm_api_key is not None
    assert settings.llm_price_input_per_mtok is not None
    assert settings.llm_price_output_per_mtok is not None
    return OpenAICompatibleProvider(
        name=settings.llm_provider_name or "",
        base_url=settings.llm_base_url or "",
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model or "",
        pricing=Pricing(
            input_per_mtok=settings.llm_price_input_per_mtok,
            output_per_mtok=settings.llm_price_output_per_mtok,
        ),
        timeout_seconds=settings.llm_timeout_seconds,
    )
