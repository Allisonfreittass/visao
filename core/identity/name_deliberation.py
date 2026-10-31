"""Name deliberation (master prompt §8.1, Phase 9 §8).

The audit found `record_naming_decision` never called outside tests: there was no way for a
name to be decided at all. This module is that mechanism.

- Triggered by real events only: the interlocutor asking about the name, or the autonomous cycle
  noticing the identity question is unresolved. Never on every conversation, never forced.
- A minimum interval between deliberations prevents loops.
- No candidate names are given. The model gets facts of its own autobiography and may choose,
  defer or decline; a choice must list the alternatives it actually considered.
- Recorded append-only through `record_naming_decision`; the owner who asked is notified of a
  choice.
"""

import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.identity.naming import NamingDecision, record_naming_decision
from core.initiatives.notify import notify
from infrastructure.database.models import (
    AgentIdentity,
    Conversation,
    IdentityNameEvent,
    IdentityVoiceEvent,
    MemoryRecord,
    ModelUsage,
    User,
)
from infrastructure.jobs import queue
from integrations.llm.base import ChatMessage, LLMProvider

JOB_KIND = "name_deliberation"
PURPOSE = "name_deliberation"
MIN_INTERVAL = timedelta(days=3)

NAME_QUESTION = re.compile(
    r"(?i)(\bseu nome\b|\bteu nome\b|como (você|vc|tu) se chama|como te chamo|"
    r"escolheu (um|o seu|seu) nome|tem (um )?nome\b|qual (é )?o seu nome|"
    r"\bum nome (para|pra) (você|vc|ti)\b)"
)

INSTRUCTIONS = """\
Contexto: este sistema tem um identificador técnico e nenhum nome pessoal obrigatório. Um evento
real trouxe a questão do nome (descrito abaixo). Cabe só a este sistema decidir. Não há resposta
esperada nem prazo: é legítimo adotar um nome, adiar ou recusar ter um nome pessoal por agora.

Considere apenas os fatos abaixo (sua autobiografia registrada). Se adotar um nome, ele deve ter
sentido para você a partir desses fatos ou do que você sabe; liste as alternativas que você
efetivamente considerou. Não adote nomes de marcas, de pessoas reais ou de personagens protegidos.

Responda SOMENTE com JSON válido:
{"action": "choose|defer|decline", "name": "nome ou null",
 "alternatives_considered": ["..."], "rationale": "justificativa breve"}
"""


class DeliberationOutputError(Exception):
    pass


def asks_about_name(text: str) -> bool:
    return bool(NAME_QUESTION.search(text))


def last_event(session: Session, identity: AgentIdentity) -> IdentityNameEvent | None:
    return session.scalar(
        select(IdentityNameEvent)
        .where(IdentityNameEvent.identity_id == identity.id)
        .order_by(IdentityNameEvent.created_at.desc())
        .limit(1)
    )


def history_summary(session: Session, identity: AgentIdentity) -> str | None:
    events = list(
        session.scalars(
            select(IdentityNameEvent)
            .where(IdentityNameEvent.identity_id == identity.id)
            .order_by(IdentityNameEvent.created_at)
        )
    )
    if not events:
        return None
    parts = []
    for event in events[-3:]:
        what = {
            "CHOSEN": f"adotou '{event.new_name}'",
            "CHANGED": f"mudou para '{event.new_name}'",
            "DEFERRED": "adiou",
            "DECLINED": "recusou por agora",
        }.get(event.event_type, "?")
        parts.append(f"em {event.created_at:%Y-%m-%d} {what} ({event.rationale_summary[:160]})")
    return "; ".join(parts)


def _due(session: Session, identity: AgentIdentity, now: datetime) -> bool:
    event = last_event(session, identity)
    if event is None:
        return True
    created = event.created_at if event.created_at.tzinfo else event.created_at.replace(tzinfo=UTC)
    return now - created >= MIN_INTERVAL


def request(
    session: Session,
    *,
    identity: AgentIdentity,
    owner: User,
    reason: str,
    now: datetime | None = None,
) -> bool:
    """Queues one deliberation if none ran recently. Idempotent per day. Returns whether queued."""
    now = now or datetime.now(UTC)
    if not _due(session, identity, now):
        return False
    queue.enqueue(
        session,
        kind=JOB_KIND,
        payload={"owner_id": str(owner.id), "reason": reason[:300]},
        idempotency_key=f"name:{identity.id}:{now:%Y-%m-%d}",
        reason=f"Deliberação sobre o nome: {reason[:200]}",
        owner_user_id=owner.id,
    )
    return True


def _facts(session: Session, identity: AgentIdentity) -> str:
    voice = session.scalar(
        select(IdentityVoiceEvent)
        .where(IdentityVoiceEvent.identity_id == identity.id)
        .order_by(IdentityVoiceEvent.created_at.desc())
        .limit(1)
    )
    conversations = session.scalar(select(func.count()).select_from(Conversation)) or 0
    memories = session.scalar(select(func.count()).select_from(MemoryRecord)) or 0
    facts = [
        f"- Identificador técnico: {identity.id}; existe desde {identity.created_at:%Y-%m-%d}.",
        f"- Conversas registradas: {conversations}; memórias curadas: {memories}.",
    ]
    if voice is not None:
        facts.append(
            f"- Decisão anterior sobre a própria voz: {voice.event_type} {voice.new_voice or ''}"
            f" ({voice.rationale_summary[:200]})."
        )
    summary = history_summary(session, identity)
    facts.append(f"- Deliberações anteriores sobre o nome: {summary or 'nenhuma'}.")
    return "\n".join(facts)


def deliberate(
    session: Session,
    *,
    identity: AgentIdentity,
    provider: LLMProvider,
    event: str,
    notify_owner: User | None,
    max_output_tokens: int,
) -> IdentityNameEvent:
    response = provider.complete(
        [
            ChatMessage(role="system", content=INSTRUCTIONS),
            ChatMessage(
                role="user",
                content=f"Evento: {event}\n\nFatos registrados:\n{_facts(session, identity)}",
            ),
        ],
        max_output_tokens=max_output_tokens,
    )
    session.add(
        ModelUsage(
            purpose=PURPOSE,
            provider=response.provider,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
            outcome="success",
        )
    )
    match = re.search(r"\{.*\}", response.text, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or data.get("action") not in {"choose", "defer", "decline"}:
        session.commit()
        raise DeliberationOutputError("unreadable deliberation")

    action = data["action"]
    name = str(data.get("name") or "").strip() if action == "choose" else None
    alternatives = [str(a)[:64] for a in data.get("alternatives_considered") or []][:10]
    recorded = record_naming_decision(
        session,
        identity,
        NamingDecision(
            action=action,
            name=name or None,
            alternatives_considered=alternatives,
            context_summary=event[:500],
            rationale_summary=str(data.get("rationale") or "(sem justificativa)")[:1000],
            model_provider=response.provider,
            model_version=response.model,
        ),
    )
    if recorded.event_type in ("CHOSEN", "CHANGED") and notify_owner is not None:
        notify(
            session,
            owner=notify_owner,
            kind="identity",
            title=f"Decidi um nome: {recorded.new_name}",
            body=recorded.rationale_summary,
        )
        session.commit()
    return recorded


def run_job(
    session: Session,
    payload: dict,
    *,
    provider: LLMProvider,
    identity: AgentIdentity,
    max_output_tokens: int,
) -> dict:
    owner = session.get(User, uuid.UUID(payload["owner_id"])) if payload.get("owner_id") else None
    event = deliberate(
        session,
        identity=identity,
        provider=provider,
        event=payload.get("reason") or "questão do nome",
        notify_owner=owner,
        max_output_tokens=max_output_tokens,
    )
    return {"event_type": event.event_type, "name": event.new_name}
