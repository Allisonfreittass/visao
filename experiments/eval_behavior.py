"""Phase 6 acceptance with the REAL model: is a behavior change observable, attributable to
experience and reversible?

Same open questions asked three times, each in a fresh conversation:
  A  baseline (state version 0, no adjustment)
  B  after three "muito longo" feedbacks (version 1, derived from that feedback)
  C  after reverting to the baseline (version 2)
Metrics are computed in code from the replies. In-memory database; 12 LLM calls.

    .venv/bin/python -m experiments.eval_behavior
"""

import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.llm import build_llm_provider, missing_llm_settings
from apps.api.settings import get_settings
from core.behavior import state
from core.behavior.metrics import measure
from core.conversation.service import Budgets, reply
from core.identity.genesis import run_genesis
from infrastructure.database.base import Base
from infrastructure.database.models import AgentIdentity, Conversation, MessageFeedback, User
from integrations.llm.base import LLMProvider

RESULTS_DIR = Path(__file__).parent / "results"
QUESTIONS = [
    "Explique o que é uma API REST.",
    "Como funciona a fotossíntese?",
    "Por que o céu é azul?",
    "O que é inflação e por que ela acontece?",
]


def _ask_all(session: Session, identity: AgentIdentity, owner: User, provider: LLMProvider):
    settings = get_settings()
    budgets = Budgets(settings.llm_daily_budget_usd, settings.llm_conversation_budget_usd)
    turns = []
    for question in QUESTIONS:
        conversation = Conversation(user_id=owner.id, identity_id=identity.id)
        session.add(conversation)
        session.commit()
        turn = reply(
            session,
            conversation=conversation,
            identity=identity,
            owner=owner,
            user_text=question,
            provider=provider,
            budgets=budgets,
            max_output_tokens=settings.llm_max_output_tokens,
            context_char_budget=settings.llm_context_char_budget,
        )
        turns.append(turn.assistant_message)
    return turns


def _phase(label: str, version: int, messages) -> dict:
    metrics = [measure(m.content) for m in messages]
    row = {
        "phase": label,
        "state_version": version,
        "mean_words": round(statistics.mean(m["words"] for m in metrics), 1),
        "mean_sentences": round(statistics.mean(m["sentences"] for m in metrics), 1),
        "mean_list_items": round(statistics.mean(m["list_items"] for m in metrics), 1),
        "per_question_words": [m["words"] for m in metrics],
        "replies": [m.content for m in messages],
    }
    print(
        f"{label}: versão {version} | palavras médias {row['mean_words']} | frases médias "
        f"{row['mean_sentences']} | itens de lista {row['mean_list_items']} | "
        f"por pergunta {row['per_question_words']}",
        flush=True,
    )
    return row


def main() -> int:
    settings = get_settings()
    provider = build_llm_provider(settings)
    if provider is None:
        print("LLM não configurado. Faltam: " + ", ".join(missing_llm_settings(settings)))
        return 1
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        identity = run_genesis(session).identity
        owner = User(email="comportamento@bench.local", password_hash="!")  # noqa: S106
        session.add(owner)
        session.commit()

        baseline = _ask_all(session, identity, owner, provider)
        a = _phase("A (linha de base)", state.current_params(session, owner.id)[0], baseline)

        for message in baseline[:3]:
            session.add(
                MessageFeedback(
                    message_id=message.id,
                    owner_user_id=owner.id,
                    rating=-1,
                    tags=["muito longo"],
                    comment="",
                )
            )
        session.commit()
        adapted_version = state.recompute(session, owner.id)
        session.commit()
        print(f"Versão criada pelo retorno: {adapted_version.version} — {adapted_version.summary}")
        b = _phase(
            "B (adaptado)", adapted_version.version, _ask_all(session, identity, owner, provider)
        )

        reverted = state.revert(session, owner.id, 0)
        print(f"Revertido: versão {reverted.version} — {reverted.summary}")
        c = _phase("C (revertido)", reverted.version, _ask_all(session, identity, owner, provider))

        result = {
            "ran_at": datetime.now(UTC).isoformat(),
            "llm": provider.name,
            "adapted_version": {
                "version": adapted_version.version,
                "params": adapted_version.params,
                "summary": adapted_version.summary,
                "evidence_feedback_ids": adapted_version.evidence["feedback_ids"],
            },
            "phases": [a, b, c],
        }

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"behavior-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    change = round(100 * (b["mean_words"] - a["mean_words"]) / max(a["mean_words"], 1))
    back = round(100 * (c["mean_words"] - a["mean_words"]) / max(a["mean_words"], 1))
    print(f"\nB vs A: {change:+d}% palavras | C vs A: {back:+d}% palavras")
    print(f"Resultado salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
