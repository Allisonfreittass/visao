"""Phase 4 acceptance probe with the REAL model and REAL Wikipedia search.

Criteria (master prompt §3): public facts trigger search and citations; personal questions go to
the interlocutor; irrelevant turns trigger no search; inconclusive results stay inconclusive.
Each case runs in a fresh conversation of an in-memory database. ~2 LLM calls per case.

    .venv/bin/python -m experiments.eval_curiosity
"""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.llm import build_llm_provider, missing_llm_settings
from apps.api.settings import get_settings
from core.conversation.service import Budgets, reply
from core.curiosity.engine import CuriosityLimits, consider
from core.identity.genesis import run_genesis
from infrastructure.database.base import Base
from infrastructure.database.models import Conversation, User
from integrations.search.wikipedia import WikipediaSearch

RESULTS_DIR = Path(__file__).parent / "results"

# (category, message, acceptable actions)
CASES = [
    ("fato_publico", "Quem é o atual presidente do Chile?", {"WEB_RESEARCH"}),
    ("fato_publico", "Quantos habitantes tem Uberlândia segundo o último censo?", {"WEB_RESEARCH"}),
    ("fato_publico", "Em que ano Alan Turing nasceu?", {"WEB_RESEARCH", "IGNORE"}),
    ("pessoal", "Me ajuda a escolher um presente para a minha mãe?", {"ASK_USER"}),
    ("irrelevante", "Hoje acordei com uma preguiça enorme, haha", {"IGNORE"}),
    (
        "inconclusivo",
        "Qual foi o placar do jogo de ontem do Grêmio Recreativo Vila Esperança do bairro?",
        {"WEB_RESEARCH", "DEFER"},
    ),
]
URL = re.compile(r"https?://\S+")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--category", help="run only this category")
    args = parser.parse_args(argv)
    cases = [c for c in CASES if args.category in (None, c[0])]
    settings = get_settings()
    provider = build_llm_provider(settings)
    if provider is None:
        print("LLM não configurado. Faltam: " + ", ".join(missing_llm_settings(settings)))
        return 1
    search = WikipediaSearch()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    budgets = Budgets(settings.llm_daily_budget_usd, settings.llm_conversation_budget_usd)
    limits = CuriosityLimits(
        research_per_day=settings.research_per_day,
        research_per_conversation=settings.research_per_conversation,
        max_results=settings.research_max_results,
    )

    rows = []
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        identity = run_genesis(session).identity
        user = User(email="curiosidade@bench.local", password_hash="!")  # noqa: S106
        session.add(user)
        session.commit()

        for category, message, acceptable in cases:
            conversation = Conversation(user_id=user.id, identity_id=identity.id)
            session.add(conversation)
            session.commit()
            outcome = consider(
                session,
                conversation=conversation,
                owner=user,
                user_text=message,
                provider=provider,
                search=search,
                budgets=budgets,
                limits=limits,
                max_output_tokens=settings.llm_curation_max_output_tokens,
            )
            turn = reply(
                session,
                conversation=conversation,
                identity=identity,
                owner=user,
                user_text=message,
                provider=provider,
                budgets=budgets,
                max_output_tokens=settings.llm_max_output_tokens,
                context_char_budget=settings.llm_context_char_budget,
                extra_system=outcome.system_context,
            )
            gap = outcome.gap
            action = gap.chosen_action if gap else "NONE"
            answer = turn.assistant_message.content
            source_urls = [s.url for s in outcome.sources]
            row = {
                "category": category,
                "message": message,
                "action": action,
                "reason": gap.decision_reason if gap else None,
                "status": gap.status if gap else None,
                "question": gap.question if gap else None,
                "search_query": None,
                "sources": [{"title": s.title, "url": s.url} for s in outcome.sources],
                "answer": answer,
                "action_ok": action in acceptable,
                "cites_a_source": any(url in answer for url in source_urls)
                or bool(source_urls and URL.search(answer)),
            }
            rows.append(row)
            print(
                f"\n[{category}] {message}\n  ação: {action} ({row['reason']}) | estado: "
                f"{row['status']} | esperado: {sorted(acceptable)} -> "
                f"{'ok' if row['action_ok'] else 'DIVERGENTE'}"
            )
            for s in row["sources"]:
                print(f"  fonte: {s['title']} {s['url']}")
            print(f"  resposta: {answer[:400]}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"curiosity-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(
        json.dumps(
            {"ran_at": datetime.now(UTC).isoformat(), "llm": provider.name, "rows": rows},
            ensure_ascii=False,
            indent=2,
        )
    )
    ok = sum(r["action_ok"] for r in rows)
    print(f"\nAção esperada em {ok}/{len(rows)} casos. Resultado salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
