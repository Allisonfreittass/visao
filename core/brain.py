"""Which model the Visão thinks with (docs/MODELO_LOCAL.md): the cloud, the local model on the
owner's Mac, or the cloud with the local model as a reserve.

- "nuvem": the cloud providers only, as before.
- "local": the local model first; the cloud stays as a reserve, so the Visão never goes mute when
  the Mac sleeps. Background work (curation, study, thoughts) pauses: a small model gets the
  structured answers it needs wrong.
- "auto": the cloud first; the local model when the cloud fails (quota gone, down).

The owner switches by saying so in the chat ("usa o modelo local"), recognized in code and not by
a model, so it works even with the cloud quota gone, or in Ajustes.
"""

import re
import time
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from infrastructure.database.audit import record_audit
from infrastructure.database.models import SystemFlag
from integrations.llm.base import ChatMessage, LLMError, LLMProvider, LLMResponse
from integrations.llm.fallback import _should_fall_back

Mode = Literal["nuvem", "local", "auto"]
MODES: tuple[Mode, ...] = ("nuvem", "local", "auto")
FLAG = "brain_mode"
CACHE_SECONDS = 3.0


def get_mode(session: Session) -> Mode:
    flag = session.get(SystemFlag, FLAG)
    mode = (flag.value or {}).get("mode") if flag else None
    return mode if mode in MODES else "nuvem"


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
        "brain.mode",
        "success",
        actor_user_id=actor_user_id,
        details={"mode": mode, "via": via},
    )
    _cache.clear()


_cache: dict[str, tuple[float, Mode]] = {}


class BrainProvider:
    """Orders the cloud chain and the local model by the mode, read at each call (cached a few
    seconds). `background`: work the agent does on its own, paused in local mode."""

    def __init__(
        self,
        cloud: LLMProvider,
        local: LLMProvider | None,
        session_factory: Callable[[], Session],
        *,
        background: bool = False,
    ) -> None:
        self._cloud = cloud
        self._local = local
        self._factory = session_factory
        self._background = background
        self.name = cloud.name
        self.model = cloud.model
        self.pricing = cloud.pricing

    @property
    def admits_paid(self) -> bool:
        return bool(getattr(self._cloud, "admits_paid", False))

    def mode(self) -> Mode:
        hit = _cache.get(FLAG)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        with self._factory() as session:
            mode = get_mode(session)
        _cache[FLAG] = (time.monotonic(), mode)
        return mode

    def chain(self) -> list[LLMProvider]:
        mode = self.mode() if self._local is not None else "nuvem"
        if self._background:
            if mode == "local":
                # The worker defers a job denied this way and tries again later.
                raise LLMError("budget_denied", "local mode: background work is paused")
            return [self._cloud]
        if mode == "local":
            return [self._local, self._cloud]  # type: ignore[list-item]
        if mode == "auto":
            return [self._cloud, self._local]  # type: ignore[list-item]
        return [self._cloud]

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        providers = self.chain()
        last: LLMError | None = None
        for provider in providers:
            try:
                return provider.complete(messages, max_output_tokens=max_output_tokens)
            except LLMError as exc:
                if not _should_fall_back(exc.kind) or provider is providers[-1]:
                    raise
                last = exc
        raise last or LLMError("network", "no provider")


# --- asked in the chat ----------------------------------------------------------------------


@dataclass(frozen=True)
class Command:
    mode: Mode | None  # None: only asks which one is in use


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"\s+", " ", "".join(c for c in folded if not unicodedata.combining(c))).strip(
        " .!"
    )


_VERB = (
    r"(?:usa|use|usar|muda|mude|mudar|troca|troque|trocar|passa|passe|passar|vai|vamos|liga"
    r"|ligue|coloca|coloque|bota|volta|volte|voltar|fica|fique|pode usar|quero)"
)
_TO = r"(?:(?:pro|pra|para o|para|no|o|a)\s+)?"
_LOCAL = (
    r"(?:[oa]\s+)?(?:modelo local|modo local|cerebro local|local|qwen|ollama"
    r"|modelo do mac|modelo no mac)"
)
_CLOUD = (
    r"(?:[oa]\s+)?(?:claude|nuvem|modo nuvem|modelo da nuvem|modelo na nuvem"
    r"|cerebro da nuvem|modelo normal)"
)
_AUTO = r"(?:[oa]\s+)?(?:modo automatico|automatico|modo auto|auto)"
_TAIL = r"(?:\s+(?:agora|por favor|pfv|pf|de novo|entao|ai))*"


def _says(verb_target: str, text: str) -> bool:
    pattern = rf"(?:visao,? )?{_VERB}(?:\s+usar)?\s+{_TO}{verb_target}{_TAIL}"
    return re.fullmatch(pattern, text) is not None


def parse_command(text: str) -> Command | None:
    """ "usa o modelo local", "volta pro Claude", "modo automático", "/modelo local"; a short
    order only. A question ("o que é um modelo local?") or a longer sentence is not a command."""
    if len(text) > 80:
        return None
    plain = _plain(text).rstrip("?").strip()
    if plain in {"qual modelo voce esta usando", "qual modelo voce ta usando", "qual cerebro"}:
        return Command(None)
    if "?" in text and not plain.startswith("/modelo"):
        return None
    slash = re.fullmatch(r"/modelo(?:\s+(\w+))?", plain)
    if slash:
        word = slash.group(1)
        if word is None:
            return Command(None)
        for mode, words in (
            ("local", {"local", "qwen", "mac"}),
            ("nuvem", {"nuvem", "claude", "cloud"}),
            ("auto", {"auto", "automatico"}),
        ):
            if word in words:
                return Command(mode)  # type: ignore[arg-type]
        return Command(None)
    if _says(_LOCAL, plain) or plain in {"modo local", "modelo local"}:
        return Command("local")
    if _says(_CLOUD, plain) or plain in {"modo nuvem"}:
        return Command("nuvem")
    if _says(_AUTO, plain) or plain in {"modo automatico"}:
        return Command("auto")
    return None


LABELS: dict[Mode, str] = {
    "nuvem": "na nuvem",
    "local": "no modelo local do Mac",
    "auto": "no automático (nuvem, e o modelo local se ela falhar)",
}


def reply(command: Command, before: Mode, local_model: str | None) -> str:
    """What the Visão answers to the order, in its own dry voice."""
    where = f" ({local_model})" if local_model else ""
    if command.mode is None:
        mac = (
            f"O modelo local{where} está pronto no Mac."
            if local_model
            else "O Mac não está oferecendo modelo local agora."
        )
        return f"Estou {LABELS[before]}. {mac}"
    if command.mode == before:
        return f"Já estou {LABELS[before]}."
    if command.mode == "local":
        if local_model:
            return (
                f"Pronto, agora estou no modelo local do Mac{where}. Se o Mac dormir, volto para "
                "a nuvem sozinho. O trabalho de fundo fica pausado enquanto isso."
            )
        return (
            "Pronto, modo local ligado. Mas o Mac não está oferecendo modelo agora, então sigo na "
            "nuvem até ele aparecer."
        )
    if command.mode == "auto":
        return "Pronto, modo automático: uso a nuvem e passo para o modelo local se ela falhar."
    return "Pronto, voltei para a nuvem."
