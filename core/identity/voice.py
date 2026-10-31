"""The agent's voice: an audited decision of the agent, among voices a human approved.

Same principles as the name (docs/AUTONOMOUS_NAMING.md): nothing is imposed, the agent may
choose, defer or decline, every decision is recorded append-only, and changing voice never
changes the UUID or anything else. The voice never drifts on its own with "personality"
(master prompt section 11): only a recorded decision changes it.

The agent cannot hear audio. Its choice is made over the facts in the catalog (engine, timbre,
measured latency, license), which is stated to it explicitly.
"""

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.database.audit import record_audit
from infrastructure.database.models import AgentIdentity, IdentityVoiceEvent
from integrations.llm.base import ChatMessage, LLMProvider
from integrations.tts.catalog import VoiceSpec, system_default


class VoiceEventType(StrEnum):
    CHOSEN = "CHOSEN"
    CHANGED = "CHANGED"
    DEFERRED = "DEFERRED"
    DECLINED = "DECLINED"


VoiceSource = Literal["chosen", "system_default", "none"]


@dataclass(frozen=True)
class ResolvedVoice:
    spec: VoiceSpec | None
    source: VoiceSource


@dataclass(frozen=True)
class VoiceDecision:
    action: Literal["choose", "defer", "decline"]
    rationale_summary: str
    model_provider: str
    model_version: str
    voice_id: str | None = None


def resolve_voice(identity: AgentIdentity, approved: list[VoiceSpec]) -> ResolvedVoice:
    """The agent's chosen voice if it is still approved; otherwise the objective system default
    (labelled as such, never presented as the agent's choice)."""
    by_id = {spec.id: spec for spec in approved}
    if identity.chosen_voice and identity.chosen_voice in by_id:
        return ResolvedVoice(by_id[identity.chosen_voice], "chosen")
    default = system_default(approved)
    return ResolvedVoice(default, "system_default" if default else "none")


def record_voice_decision(
    session: Session,
    identity: AgentIdentity,
    decision: VoiceDecision,
    approved: list[VoiceSpec],
) -> IdentityVoiceEvent:
    for label, value in (
        ("rationale_summary", decision.rationale_summary),
        ("model_provider", decision.model_provider),
        ("model_version", decision.model_version),
    ):
        if not value.strip():
            raise ValueError(f"{label} is required")
    approved_ids = [spec.id for spec in approved]
    previous = identity.chosen_voice

    if decision.action == "choose":
        if decision.voice_id not in approved_ids:
            raise ValueError("a choice must be one of the approved voices")
        if decision.voice_id == previous:
            raise ValueError("voice is unchanged")
        event_type = VoiceEventType.CHOSEN if previous is None else VoiceEventType.CHANGED
    elif decision.voice_id is not None:
        raise ValueError("only a choice carries a voice")
    else:
        event_type = (
            VoiceEventType.DEFERRED if decision.action == "defer" else VoiceEventType.DECLINED
        )

    event = IdentityVoiceEvent(
        identity_id=identity.id,
        event_type=event_type,
        previous_voice=previous,
        new_voice=decision.voice_id,
        options_offered=approved_ids,
        rationale_summary=decision.rationale_summary[:2000],
        model_provider=decision.model_provider,
        model_version=decision.model_version,
    )
    session.add(event)
    if decision.action == "choose":
        identity.chosen_voice = decision.voice_id
    record_audit(
        session,
        "identity.voice_decision",
        "success",
        details={"identity_id": str(identity.id), "event_type": event_type},
    )
    session.commit()
    return event


def voice_history(session: Session, identity: AgentIdentity) -> list[IdentityVoiceEvent]:
    return list(
        session.scalars(
            select(IdentityVoiceEvent)
            .where(IdentityVoiceEvent.identity_id == identity.id)
            .order_by(IdentityVoiceEvent.created_at)
        )
    )


# --- Deliberation -----------------------------------------------------------------------------

DELIBERATION_INSTRUCTIONS = """\
Contexto: uma capacidade nova ficou disponível neste sistema, a síntese de voz. Uma pessoa
avaliou as vozes instaladas e aprovou apenas as listadas abaixo como tecnicamente aceitáveis.
A decisão sobre qual voz usar como própria cabe a você, e não há resposta esperada: você pode
escolher uma das opções, adiar a decisão ou recusar ter uma voz própria por enquanto. Enquanto
não houver escolha, o sistema usa uma voz padrão técnica (a de menor latência), registrada como
padrão do sistema e não como escolha sua.

Limites que você deve considerar: você não consegue ouvir áudio; só tem os dados abaixo. A voz
não muda sozinha depois; só outra decisão registrada a altera.

Responda SOMENTE com JSON válido:
{"action": "choose|defer|decline", "voice_id": "id ou null", "rationale": "justificativa breve"}
"""


class DeliberationOutputError(Exception):
    pass


def _options_text(identity: AgentIdentity, approved: list[VoiceSpec]) -> str:
    lines = [
        f"Identificador técnico: {identity.id}.",
        f"Voz atual: {identity.chosen_voice or 'nenhuma escolhida'}.",
        "Opções aprovadas:",
    ]
    for spec in approved:
        lines.append(
            f"- id={spec.id}; motor={spec.engine}; timbre={spec.timbre}; "
            f"tempo até o primeiro áudio medido={spec.first_audio_s}s; "
            f"memória={spec.peak_memory_mb} MB; licença: {spec.license_note}"
        )
    return "\n".join(lines)


def parse_deliberation(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise DeliberationOutputError("no JSON object in reply")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise DeliberationOutputError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("action") not in {"choose", "defer", "decline"}:
        raise DeliberationOutputError("missing or invalid 'action'")
    return data


def deliberate_voice(
    session: Session,
    identity: AgentIdentity,
    approved: list[VoiceSpec],
    provider: LLMProvider,
    *,
    max_output_tokens: int,
) -> IdentityVoiceEvent:
    """Asks the model once, records whatever it decides. Triggered by a real event (voice became
    available or the approved list changed), never on a timer or in every conversation."""
    if not approved:
        raise ValueError("no approved voices to deliberate about")
    response = provider.complete(
        [
            ChatMessage(role="system", content=DELIBERATION_INSTRUCTIONS),
            ChatMessage(role="user", content=_options_text(identity, approved)),
        ],
        max_output_tokens=max_output_tokens,
    )
    data = parse_deliberation(response.text)
    voice_id = data.get("voice_id") if data["action"] == "choose" else None
    return record_voice_decision(
        session,
        identity,
        VoiceDecision(
            action=data["action"],
            voice_id=voice_id,
            rationale_summary=str(data.get("rationale") or "(sem justificativa)"),
            model_provider=response.provider,
            model_version=response.model,
        ),
        approved,
    )
