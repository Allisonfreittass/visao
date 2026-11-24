import logging
from collections.abc import Callable
from decimal import Decimal
from functools import lru_cache

from pydantic import SecretStr

from apps.api.settings import Settings, get_settings
from core import llm_routing
from core.arm.local_llm import LocalModelProvider
from core.brain import BrainProvider
from integrations.llm.anthropic_provider import AnthropicProvider
from integrations.llm.base import LLMProvider, Pricing, current_purpose
from integrations.llm.budget import (
    BudgetGuard,
    BudgetLimits,
    GuardedLLMProvider,
    credential_fingerprint,
)
from integrations.llm.fallback import FallbackLLMProvider
from integrations.llm.fitting import FittingProvider
from integrations.llm.openai_compatible import OpenAICompatibleProvider
from integrations.llm.pause import PauseBoard

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
    settings = get_settings()
    return with_brain(settings, build_llm_provider(settings, fast=True))


@lru_cache
def get_code_provider() -> LLMProvider | None:
    """The arm's own executor (ADR-0023): the background chain, only with the providers allowed
    to read the owner's code. None when none of them is configured."""
    return build_llm_provider(get_settings(), only=llm_routing.CODE_KINDS)


@lru_cache
def get_screen_provider() -> LLMProvider | None:
    """A reply that sees the owner's screen (docs/TELA.md): the conversation's chain, only with
    the providers allowed to see it. None when none of them is configured."""
    return build_llm_provider(get_settings(), fast=True, only=llm_routing.SCREEN_KINDS)


def with_brain(
    settings: Settings,
    cloud: LLMProvider | None,
    *,
    background: bool = False,
    session_factory=None,
) -> LLMProvider | None:
    """The cloud chain behind the owner's choice of model (core/brain.py): cloud, the local
    model on the Mac first, or the cloud with it as a reserve."""
    if cloud is None:
        return None
    if session_factory is None:
        from infrastructure.database.session import get_sessionmaker

        session_factory = get_sessionmaker()
    local = LocalModelProvider(
        session_factory,
        timeout_seconds=settings.local_llm_timeout_seconds,
        context_chars=settings.local_llm_context_chars,
    )
    return BrainProvider(cloud, local, session_factory, background=background)


def is_anthropic(name: str | None, base_url: str | None) -> bool:
    return (name or "").lower() in {"anthropic", "claude"} or "api.anthropic.com" in (
        base_url or ""
    )


# Background work (curation, review, study) keeps thinking but shallow: thinking tokens share
# max_tokens with the answer, and a deep think would cut the JSON these steps return.
ANTHROPIC_BACKGROUND = {"output_config": {"effort": "low"}}


def _openai_compatible(
    settings: Settings,
    name: str | None,
    base_url: str | None,
    api_key: SecretStr | None,
    model: str | None,
    price_in: Decimal | None,
    price_out: Decimal | None,
    extra_body: dict | None = None,
) -> LLMProvider:
    assert name and base_url and api_key and model
    assert price_in is not None and price_out is not None
    if is_anthropic(name, base_url):
        return AnthropicProvider(
            name=name,
            api_key=api_key.get_secret_value(),
            model=model,
            pricing=Pricing(input_per_mtok=price_in, output_per_mtok=price_out),
            timeout_seconds=settings.llm_timeout_seconds,
            extra_body=extra_body if extra_body is not None else ANTHROPIC_BACKGROUND,
            base_url=None if "api.anthropic.com" in base_url else base_url,
        )
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


def chained_slots(settings: Settings, *, warn: bool = False) -> list[str]:
    """Setting prefixes of the providers in the chain, in configured order: the primary, the
    fallback when complete, and the second fallback when complete too (a second one without a
    first is not chained). A partial one is ignored, with a warning."""
    if missing_llm_settings(settings):
        return []
    slots = ["llm_"]
    for slot in ("fallback", "fallback2"):
        missing = missing_fallback_settings(settings, slot)
        if missing and len(missing) < 6 and warn:
            logger.warning(
                f"LLM {slot} ignored, missing: " + ", ".join(missing),
                extra={"event": "llm_fallback_incomplete"},
            )
        if missing:
            break
        slots.append(f"llm_{slot}_")
    return slots


def configured_kinds(settings: Settings) -> list[llm_routing.Kind]:
    """Claude, OpenAI, Gemini or another, for each provider in the chain (Ajustes shows them)."""
    return [
        llm_routing.provider_kind(
            getattr(settings, f"{prefix}provider_name"), getattr(settings, f"{prefix}base_url")
        )
        for prefix in chained_slots(settings)
    ]


def _session_factory():
    from infrastructure.database.session import get_sessionmaker

    return get_sessionmaker()()


def _routed_order(kinds: list[llm_routing.Kind], factory) -> Callable[[], list[int]]:
    """The order per task (core/llm_routing.py), read at each call from the owner's switch."""

    def order() -> list[int]:
        return llm_routing.order(kinds, current_purpose(), llm_routing.cached_mode(factory))

    return order


def build_llm_provider(
    settings: Settings,
    *,
    budget_guard: BudgetGuard | None = None,
    fast: bool = False,
    session_factory=None,
    only: tuple[llm_routing.Kind, ...] | None = None,
) -> LLMProvider | None:
    """Returns None unless every primary setting, prices included, is present. A fully
    configured fallback is chained after the primary; a partial one is ignored with a warning.
    With more than one provider, the owner's switch may reorder them per task (ADR-0022).
    `only`: the kinds allowed in this chain; the others are left out of it entirely."""
    if missing_llm_settings(settings):
        return None
    factory = session_factory or _session_factory
    if budget_guard is None:
        budget_guard = BudgetGuard(
            factory,
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
            paid_daily_usd=settings.llm_paid_daily_usd,
            paid_monthly_usd=settings.llm_paid_monthly_usd,
        )
    chain: list[LLMProvider] = []
    kinds: list[llm_routing.Kind] = []
    for prefix in chained_slots(settings, warn=True):
        name = getattr(settings, f"{prefix}provider_name")
        base_url = getattr(settings, f"{prefix}base_url")
        api_key = getattr(settings, f"{prefix}api_key")
        kind = llm_routing.provider_kind(name, base_url)
        if only is not None and kind not in only:
            continue
        raw = _openai_compatible(
            settings,
            name,
            base_url,
            api_key,
            getattr(settings, f"{prefix}model"),
            getattr(settings, f"{prefix}price_input_per_mtok"),
            getattr(settings, f"{prefix}price_output_per_mtok"),
            getattr(settings, f"{prefix}fast_extra_body") if fast else None,
        )
        chain.append(
            FittingProvider(
                GuardedLLMProvider(
                    raw,
                    base_url,
                    budget_guard,
                    credential_fingerprint(api_key.get_secret_value()),
                ),
                getattr(settings, f"{prefix}max_request_tokens"),
            )
        )
        kinds.append(kind)
    if not chain:
        return None
    if len(chain) == 1:
        return chain[0]
    return FallbackLLMProvider(
        chain, order=_routed_order(kinds, factory), pauses=PauseBoard(factory)
    )
