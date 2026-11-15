"""Reply length in the chat, with the REAL model and the prompt the app uses (mind on).

Run once before and once after a change to the style layer (core/conversation/style.py) and
compare: words, paragraphs and bubbles per reply, computed in code. Chat questions should come
out short; the code question is the control (it may stay long). In-memory database; one call per
question.

    .venv/bin/python -m experiments.eval_brevity antes
    .venv/bin/python -m experiments.eval_brevity depois
"""

import json
import re
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.llm import build_llm_provider, missing_llm_settings
from apps.api.settings import get_settings
from core.behavior.metrics import measure
from core.conversation.service import Budgets, reply
from core.identity.capabilities import Capabilities
from core.identity.genesis import run_genesis
from core.mind import state as mind_state
from infrastructure.database.base import Base
from infrastructure.database.models import Conversation, User

RESULTS_DIR = Path(__file__).parent / "results"
CHAT = [
    "quanto custa viajar pro Chile em agosto de 2027 a dois?",
    "vale a pena ir pra Santiago no inverno?",
    "tô pensando em trocar de emprego, mas tenho medo. o que você acha?",
    "me explica rapidinho o que é inflação",
    "qual a diferença entre hostel e hotel?",
]
CONTROL = ["escreve uma função em Python que remove duplicados de uma lista mantendo a ordem"]


def _paragraphs(text: str) -> int:
    return len([p for p in re.split(r"\n\s*\n", text) if p.strip()])


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "rodada"
    settings = get_settings()
    provider = build_llm_provider(settings)
    if provider is None:
        print("LLM não configurado. Faltam: " + ", ".join(missing_llm_settings(settings)))
        return 1
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    rows = []
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        identity = run_genesis(session).identity
        owner = User(email="brevidade@bench.local", password_hash="!")  # noqa: S106
        session.add(owner)
        session.commit()
        budgets = Budgets(settings.llm_daily_budget_usd, settings.llm_conversation_budget_usd)
        for question in CHAT + CONTROL:
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
                capabilities=Capabilities(browser=True, pages=True, research_source="a web"),
                self_text=mind_state.current_self(session),
            )
            message = turn.assistant_message
            rows.append(
                {
                    "question": question,
                    "control": question in CONTROL,
                    "words": measure(message.content)["words"],
                    "paragraphs": _paragraphs(message.content),
                    "bubbles": len(message.parts or [message.content]),
                    "reply": message.content,
                }
            )
            print(f"{rows[-1]['words']:4d} palavras | {rows[-1]['bubbles']} bolha(s) | {question}")
    chat = [r for r in rows if not r["control"]]
    summary = {
        "label": label,
        "ran_at": datetime.now(UTC).isoformat(),
        "llm": provider.name,
        "chat_mean_words": round(statistics.mean(r["words"] for r in chat), 1),
        "chat_mean_paragraphs": round(statistics.mean(r["paragraphs"] for r in chat), 1),
        "chat_mean_bubbles": round(statistics.mean(r["bubbles"] for r in chat), 1),
        "control_words": [r["words"] for r in rows if r["control"]],
        "rows": rows,
    }
    print(
        f"{label}: conversa {summary['chat_mean_words']} palavras, "
        f"{summary['chat_mean_paragraphs']} parágrafos, {summary['chat_mean_bubbles']} bolhas; "
        f"controle (código) {summary['control_words']} palavras"
    )
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"brevity-{label}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Resultado: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
