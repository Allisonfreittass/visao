"""Decision layer (Phase 9 §12): what the system decided and actually did this turn.

Assembled in code from the subsystems (curiosity, memory, continuity, identity), not by an extra
model call. The expression layer (the reply) receives the executed actions as facts and is told
not to claim anything else; the record is persisted for audit and metrics.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from infrastructure.database.models import Decision

# How each executed action is stated to the expression layer.
_DESCRIBE = {
    "ask_question": "há uma lacuna que só o interlocutor pode responder (pergunta indicada acima)",
    "research": "pesquisa feita agora; fontes listadas acima",
    "research_deferred": "pesquisa adiada por orçamento; nada foi pesquisado agora",
    "conversation_thread_detected": (
        "uma pendência de conversa foi registrada para possível retomada; nenhuma pesquisa"
        " externa foi feita. O envio futuro depende da avaliação do worker"
    ),
    "goal_proposed": "proposta de meta registrada; só roda com aprovação",
    "continuity": "investigações anteriores relacionadas foram consultadas no registro",
    "recall_study": "o caderno de estudos foi consultado; use o estado e as evidências reais",
    "name_deliberation_requested": (
        "uma deliberação sobre o nome foi agendada para o worker; o resultado ainda não está"
        " disponível. Há um mecanismo de aviso do resultado, inclusive adiamento ou recusa,"
        " sujeito aos horários de silêncio, à pausa de autonomia e ao limite de avisos"
    ),
    "name_deliberation_recent": "o nome já foi deliberado recentemente; não houve nova deliberação",
}


@dataclass
class TurnPlan:
    actions: list[dict[str, Any]] = field(default_factory=list)

    def add(self, action: str, *, executed: bool, reason: str, **details: Any) -> None:
        self.actions.append({"action": action, "executed": executed, "reason": reason, **details})

    def executed(self) -> list[str]:
        return [a["action"] for a in self.actions if a["executed"]]

    def facts(self) -> str:
        done = [_DESCRIBE[a] for a in self.executed() if a in _DESCRIBE]
        if not done:
            return (
                "Ações executadas neste turno além de responder: nenhuma. Não afirmar ter "
                "pesquisado, registrado ou agendado algo."
            )
        return (
            "Ações novas executadas neste turno (afirmar só estas): "
            + "; ".join(done)
            + ". Relatos de ações anteriores podem usar o histórico registrado, distinguindo "
            "tentativa de pesquisa, conclusão e ação executada agora."
        )

    def persist(
        self,
        session: Session,
        *,
        owner_id: uuid.UUID | None,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        origin: str = "turn",
    ) -> Decision:
        decision = Decision(
            owner_user_id=owner_id,
            conversation_id=conversation_id,
            message_id=message_id,
            origin=origin,
            actions=self.actions,
        )
        session.add(decision)
        session.flush()
        return decision
