"""The local model on the owner's Mac, reached through the arm (docs/MODELO_LOCAL.md).

The server cannot reach the Mac (no port open at home), so it writes the question in the
database and waits; the arm, which already asks the server for work from the inside out, takes it,
asks the model running on the Mac (Ollama) and sends back only the text. To the rest of the
server this is one more LLMProvider, priced at zero.

A Mac that is off, asleep or offers no local model fails at once with a kind the fallback chain
moves past ("network"), so the conversation goes to the cloud instead of waiting.
"""

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.database.models import ArmDevice, ArmLlmCall
from integrations.llm.base import ChatMessage, LLMError, LLMResponse, Pricing, should_stop

PROVIDER_NAME = "local"
# The arm asks again every 25 s; a Mac that has not asked for longer than this is gone.
LOCAL_WINDOW = timedelta(seconds=60)
# A question nobody took in this long is dropped: the server stopped waiting for it.
PENDING_TTL = timedelta(minutes=3)
MAX_RESULT = 100_000
POLL_SECONDS = 0.25


def _now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def available(
    session: Session, owner_user_id: uuid.UUID | None = None, now: datetime | None = None
) -> ArmDevice | None:
    """The Mac that offers a local model and asked for work a moment ago, if any."""
    now = now or _now()
    query = select(ArmDevice).where(ArmDevice.local_model.is_not(None))
    if owner_user_id is not None:
        query = query.where(ArmDevice.owner_user_id == owner_user_id)
    devices = session.scalars(query.order_by(ArmDevice.local_seen_at.desc())).all()
    for device in devices:
        seen = _utc(device.local_seen_at)
        if seen is not None and now - seen < LOCAL_WINDOW:
            return device
    return None


def trim(messages: list[ChatMessage], max_chars: int) -> list[ChatMessage]:
    """A small model reads little at once: keep the system messages and the most recent turns
    that fit, always the last one. Ollama would otherwise cut from the start, losing who it is."""
    system = [m for m in messages if m.role == "system"]
    rest = [m for m in messages if m.role != "system"]
    room = max_chars - sum(len(m.content) for m in system)
    kept: list[ChatMessage] = []
    for message in reversed(rest):
        if kept and len(message.content) > room:
            break
        if not kept and len(message.content) > max(room, 2000):
            message = ChatMessage(message.role, message.content[-max(room, 2000) :])
        kept.append(message)
        room -= len(message.content)
    if room < 0 and system:
        # The system prompt alone is too long: keep its start, where the identity and rules are.
        budget = max(2000, max_chars - sum(len(m.content) for m in kept))
        system = [ChatMessage("system", "\n\n".join(m.content for m in system)[:budget])]
    return system + list(reversed(kept))


class LocalModelProvider:
    """LLMProvider that answers with the model on the owner's Mac, through the arm."""

    name = PROVIDER_NAME
    pricing = Pricing(input_per_mtok=Decimal(0), output_per_mtok=Decimal(0))

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        timeout_seconds: float = 120.0,
        context_chars: int = 40_000,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._factory = session_factory
        self._timeout = timeout_seconds
        self._context_chars = context_chars
        self._sleep = sleep
        self.model = "local"

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        if any(m.images for m in messages):
            raise LLMError("bad_response", "the local model reads no pictures")
        started = time.monotonic()
        with self._factory() as session:
            device = available(session)
            if device is None:
                raise LLMError("network", "no Mac with a local model is online")
            call = ArmLlmCall(
                owner_user_id=device.owner_user_id,
                status="pending",
                model=device.local_model or "",
                payload={
                    "messages": [
                        {"role": m.role, "content": m.content}
                        for m in trim(messages, self._context_chars)
                    ],
                    "max_output_tokens": max_output_tokens,
                },
            )
            session.add(call)
            session.commit()
            call_id, self.model = call.id, call.model or "local"
        while time.monotonic() - started < self._timeout:
            self._sleep(POLL_SECONDS)
            if should_stop():
                self._expire(call_id)
                raise LLMError("cancelled", "stopped by the owner")
            with self._factory() as session:
                call = session.get(ArmLlmCall, call_id)
                if call is None:
                    raise LLMError("network", "the question disappeared")
                if call.status == "done":
                    if not call.result.strip():
                        raise LLMError("bad_response", "the local model answered nothing")
                    return LLMResponse(
                        text=call.result,
                        provider=PROVIDER_NAME,
                        model=call.model or "local",
                        input_tokens=call.input_tokens,
                        output_tokens=call.output_tokens,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        finish_reason="stop",
                        cost_usd=Decimal(0),
                    )
                if call.status == "failed":
                    raise LLMError("network", f"the Mac could not answer: {call.error}")
        self._expire(call_id)
        raise LLMError("timeout", "the local model took too long")

    def _expire(self, call_id: uuid.UUID) -> None:
        with self._factory() as session:
            call = session.get(ArmLlmCall, call_id)
            if call is not None and call.status in ("pending", "claimed"):
                call.status = "expired"
                call.finished_at = _now()
                session.commit()


# --- the Mac's side -----------------------------------------------------------------------


def seen(session: Session, device: ArmDevice, model: str | None) -> None:
    """The arm asked for a question: it is online and offers this model (None: none)."""
    model = (model or "").strip()[:64] or None
    device.local_model = model
    device.local_seen_at = _now() if model else None
    device.last_seen_at = _now()
    session.flush()


def claim(session: Session, device: ArmDevice) -> ArmLlmCall | None:
    """The oldest question of this Mac's owner still waiting, now taken by this Mac."""
    now = _now()
    for call in session.scalars(
        select(ArmLlmCall)
        .where(ArmLlmCall.owner_user_id == device.owner_user_id, ArmLlmCall.status == "pending")
        .order_by(ArmLlmCall.created_at)
    ):
        created = _utc(call.created_at)
        if created is not None and now - created > PENDING_TTL:
            call.status, call.finished_at = "expired", now
            continue
        call.status, call.device_id, call.claimed_at = "claimed", device.id, now
        session.flush()
        return call
    session.flush()
    return None


def finish(
    session: Session,
    device: ArmDevice,
    call_id: uuid.UUID,
    *,
    ok: bool,
    text: str = "",
    error: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    call = session.get(ArmLlmCall, call_id)
    if call is None or call.device_id != device.id:
        raise LookupError(call_id)
    if call.status != "claimed":
        return  # the server stopped waiting (expired): the late answer is dropped
    call.status = "done" if ok else "failed"
    call.result = text[:MAX_RESULT] if ok else ""
    call.error = "" if ok else error[:500]
    call.input_tokens, call.output_tokens = max(0, input_tokens), max(0, output_tokens)
    call.finished_at = _now()
    session.flush()
