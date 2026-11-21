"""A real turn through a model with a small limit: the reply comes, compacted by priority, and
what must never go stays (docs/MODO_COMPACTO.md). Real case (2026-11-21): Groq's free tier
answered 413 to every turn and the person got no reply."""

from dataclasses import replace
from datetime import timedelta

from core.decision.pipeline import run_turn
from core.identity.genesis import get_identity
from infrastructure.database.models import Message
from integrations.llm.base import LLMError
from integrations.llm.fitting import FittingProvider, forget_learned, tokens
from tests.fakes import FakeLLMProvider
from tests.integration.test_mind import NOON, setup
from tests.integration.test_mind_temperament import chat
from tests.integration.test_phase9 import CONFIG


class RefusesTheFirst(FakeLLMProvider):
    """Says 413 to the first request, with a limit well below what it received."""

    def complete(self, messages, *, max_output_tokens):
        if not self.prompts:
            self.prompts.append(list(messages))
            limit = int(tokens(messages) * 0.5) + max_output_tokens
            raise LLMError("too_large", f"Limit {limit}, Requested {tokens(messages)}")
        return super().complete(messages, max_output_tokens=max_output_tokens)


def test_a_turn_answers_through_a_small_model_and_keeps_the_essentials(db):
    forget_learned()
    owner = setup(db)
    conversation = chat(db, owner)
    for n in range(12):  # a long conversation: history is the first thing to go
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user" if n % 2 == 0 else "assistant",
                content=f"mensagem antiga {n} " + "treino de corrida " * 80,
                created_at=NOON - timedelta(hours=3) + timedelta(minutes=n),
            )
        )
    db.commit()
    small = RefusesTheFirst(reply_text="Que bom, me conta dos rounds.")
    outcome = run_turn(
        db,
        conversation=conversation,
        identity=get_identity(db),
        owner=owner,
        text="Fiz 3 rounds de 15 minutos no Hyrox hoje",
        provider=FittingProvider(small),
        search=None,
        config=replace(CONFIG, curiosity_enabled=False, mind_enabled=True),
    )
    assert outcome.result.assistant_message.content == "Que bom, me conta dos rounds."
    full, compact = small.prompts
    assert tokens(compact) < tokens(full)
    sent = "\n".join(m.content for m in compact)
    assert "Fiz 3 rounds de 15 minutos no Hyrox hoje" in sent  # the person's words
    assert "Nunca afirme ter feito" in sent  # the truth rules
    assert "Ações" in sent  # what was done this turn
    assert sum("mensagem antiga" in m.content for m in compact) < sum(
        "mensagem antiga" in m.content for m in full
    )
    forget_learned()
