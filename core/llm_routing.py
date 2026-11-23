"""Which cloud provider goes first for each task (ADR-0022). A rule in code, never a model.

Two modes, switched by the owner in Ajustes ("Escolha do provedor"):

- "fixa": the configured chain (VISION_LLM_*, then FALLBACK, then FALLBACK2), as before.
- "por_tarefa": the same providers, reordered by what the call is for (its ModelUsage purpose):
  - "publico", a call that carries only public text (today only the study review: a question
    already checked as public and excerpts of public pages): Gemini, Claude, OpenAI. Gemini's
    free tier may use what it receives to improve Google's products, so nothing of the owner
    goes there first.
  - "pessoal", everything else, and every call that does not say what it is for: Claude, OpenAI,
    Gemini.

Not to be confused with core/brain.py, whose "auto" puts the local model on the Mac behind the
cloud; this one only orders the cloud providers. Fallback on failure, the budget guard (paid
caps), the fitting of the prompt and the pause of a provider out of quota apply as before, to
each provider in the new order. A provider the rule does not know (Groq, OpenRouter...) keeps
its configured place after the known ones.
"""

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from infrastructure.database.audit import record_audit
from infrastructure.database.models import SystemFlag

Mode = Literal["fixa", "por_tarefa"]
MODES: tuple[Mode, ...] = ("fixa", "por_tarefa")
Kind = Literal["claude", "openai", "gemini", "outro"]
TaskClass = Literal["pessoal", "publico"]
FLAG = "llm_routing"
CACHE_SECONDS = 3.0

# Purposes whose prompt carries nothing of the owner. Adding one here is a privacy decision.
PUBLIC_PURPOSES = frozenset({"study_review"})
ORDERS: dict[TaskClass, tuple[Kind, ...]] = {
    "pessoal": ("claude", "openai", "gemini"),
    "publico": ("gemini", "claude", "openai"),
}
LABELS: dict[Kind, str] = {
    "claude": "Claude",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "outro": "outro",
}


def provider_kind(name: str | None, base_url: str | None) -> Kind:
    """Recognized by the configured name or the API's address, never by asking a model."""
    name, url = (name or "").lower(), (base_url or "").lower()
    if name in {"anthropic", "claude"} or "api.anthropic.com" in url:
        return "claude"
    if name in {"openai", "chatgpt"} or "api.openai.com" in url:
        return "openai"
    if name in {"gemini", "google"} or "generativelanguage.googleapis.com" in url:
        return "gemini"
    return "outro"


def task_class(purpose: str | None) -> TaskClass:
    return "publico" if purpose in PUBLIC_PURPOSES else "pessoal"


def order(kinds: list[Kind], purpose: str | None, mode: Mode) -> list[int]:
    """Indexes of the configured providers, in the order to try them for this call."""
    if mode != "por_tarefa":
        return list(range(len(kinds)))
    rank = ORDERS[task_class(purpose)]
    return sorted(
        range(len(kinds)),
        key=lambda i: (rank.index(kinds[i]) if kinds[i] in rank else len(rank), i),
    )


def get_mode(session: Session) -> Mode:
    flag = session.get(SystemFlag, FLAG)
    mode = (flag.value or {}).get("mode") if flag else None
    return mode if mode in MODES else "fixa"


def set_mode(session: Session, mode: Mode, *, actor_user_id: uuid.UUID | None, via: str) -> None:
    if mode not in MODES:
        raise ValueError(mode)
    flag = session.get(SystemFlag, FLAG)
    if flag is None:
        session.add(SystemFlag(name=FLAG, value={"mode": mode}))
    else:
        flag.value = {"mode": mode}
        flag.updated_at = datetime.now(UTC)
    record_audit(
        session,
        "llm.routing",
        "success",
        actor_user_id=actor_user_id,
        details={"mode": mode, "via": via},
    )
    _cache.clear()


_cache: dict[str, tuple[float, Mode]] = {}


def cached_mode(factory: Callable[[], Session]) -> Mode:
    """Read at each call, cached a few seconds (the API and the worker each keep their own)."""
    hit = _cache.get(FLAG)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with factory() as session:
        mode = get_mode(session)
    _cache[FLAG] = (time.monotonic(), mode)
    return mode
