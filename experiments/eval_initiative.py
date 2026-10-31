"""Phase 5 acceptance with the REAL model and REAL Wikipedia: an initiative triggered by a real
event (research deferred for lack of budget), run only after approval, ending in a notification
only if the sources answer the question. In-memory database; ~3 LLM calls per attempt.

    .venv/bin/python -m experiments.eval_initiative
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.llm import build_llm_provider, missing_llm_settings
from apps.api.settings import get_settings
from apps.worker.handlers import research_followup_handler
from apps.worker.runner import run_once
from core.conversation.service import Budgets
from core.curiosity.engine import CuriosityLimits, consider
from core.goals import lifecycle
from core.goals.followup import propose_followup
from core.identity.genesis import run_genesis
from infrastructure.database.base import Base
from infrastructure.database.models import (
    Conversation,
    Goal,
    KnowledgeGap,
    ModelUsage,
    Notification,
    ScheduledJob,
    User,
)
from integrations.search.wikipedia import WikipediaSearch

RESULTS_DIR = Path(__file__).parent / "results"
QUESTIONS = [
    "Em que ano foi fundada a cidade de Uberlândia?",
    "Qual é a altitude do Pico da Neblina?",
    "Em que ano foi inaugurada a Ponte Rio-Niterói?",
]


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--question", action="append", help="use these questions instead")
    parser.add_argument(
        "--seed-gap",
        metavar="SEARCH_QUERY",
        help="skip the model's assessment: start from a DEFERRED public-fact gap with this query "
        "(isolates the worker path from assessment variability)",
    )
    args = parser.parse_args(argv)
    questions = args.question or QUESTIONS
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
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    budgets = Budgets(settings.llm_daily_budget_usd, settings.llm_conversation_budget_usd)
    # The real event: no research budget left in this conversation.
    exhausted = CuriosityLimits(research_per_day=20, research_per_conversation=0, max_results=3)
    handlers = {"research_followup": research_followup_handler(settings, provider, search)}

    log: list[dict] = []
    with factory() as session:
        identity = run_genesis(session).identity
        owner = User(
            email="iniciativa@bench.local",
            password_hash="!",  # noqa: S106
            quiet_start="00:00",
            quiet_end="00:00",
        )
        session.add(owner)
        session.commit()

        goal = None
        if args.seed_gap:
            conversation = Conversation(user_id=owner.id, identity_id=identity.id)
            session.add(conversation)
            session.flush()
            seeded = KnowledgeGap(
                owner_user_id=owner.id,
                conversation_id=conversation.id,
                trigger_kind="dependency",
                depends_on="public_fact",
                question=questions[0],
                hypothesis="",
                scores={"expected_value": 0.9},
                chosen_action="DEFER",
                decision_reason="research_budget",
                status="DEFERRED",
            )
            session.add(seeded)
            session.flush()
            goal = propose_followup(session, gap=seeded, owner=owner, search_query=args.seed_gap)
            session.commit()
            log.append(
                {
                    "question": questions[0],
                    "decision": "seeded DEFER",
                    "proposed_goal": str(goal.id),
                }
            )
            print(f"- {questions[0]}\n  lacuna semeada (DEFER), consulta: {args.seed_gap}")
            questions = []
        for question in questions:
            conversation = Conversation(user_id=owner.id, identity_id=identity.id)
            session.add(conversation)
            session.commit()
            outcome = consider(
                session,
                conversation=conversation,
                owner=owner,
                user_text=question,
                provider=provider,
                search=search,
                budgets=budgets,
                limits=exhausted,
                max_output_tokens=settings.llm_curation_max_output_tokens,
            )
            gap = outcome.gap
            entry = {
                "question": question,
                "decision": f"{gap.chosen_action}/{gap.decision_reason}" if gap else None,
                "proposed_goal": str(outcome.proposed_goal.id) if outcome.proposed_goal else None,
            }
            log.append(entry)
            print(
                f"- {question}\n  decisão: {entry['decision']} | meta proposta: "
                f"{'sim' if outcome.proposed_goal else 'não'}"
            )
            if outcome.proposed_goal and outcome.proposed_goal.status == lifecycle.EVALUATED:
                goal = outcome.proposed_goal
                break

        if goal is None:
            usage = session.scalars(select(ModelUsage).order_by(ModelUsage.created_at)).all()
            print(
                "\nNenhuma meta proposta. Chamadas de avaliação: "
                + ", ".join(
                    f"{u.outcome}{'/' + u.error_kind if u.error_kind else ''}" for u in usage
                )
                + " (decisão None = avaliação falhou; IGNORE = sem lacuna)"
            )
            return 1

        print(f"\nMeta: {goal.title}\nPermissões pedidas: {goal.required_permissions}")
        jobs_before = session.scalars(select(ScheduledJob)).all()
        print(f"Trabalhos na fila antes da aprovação: {len(jobs_before)}")
        lifecycle.approve(session, goal, owner, payload={})
        print("Aprovada (simulando o clique do interlocutor).")

    outcome = run_once(factory, handlers, "eval-worker")
    print(f"Worker: {outcome}")

    with factory() as session:
        goal = session.get(Goal, goal.id)
        history = [
            f"{e.from_status}->{e.to_status} ({e.actor}: {e.reason})"
            for e in lifecycle.history(session, goal)
        ]
        notification = session.scalar(select(Notification))
        print("Histórico:\n  " + "\n  ".join(history))
        print(f"Estado final: {goal.status}")
        if notification:
            print(f"\nAVISO: {notification.title}\n{notification.body}")
        else:
            print("\nSem aviso (fontes não responderam ou nada encontrado).")
        result = {
            "ran_at": datetime.now(UTC).isoformat(),
            "attempts": log,
            "goal": {
                "title": goal.title,
                "status": goal.status,
                "history": history,
                "evidence": goal.evidence,
            },
            "notification": {"title": notification.title, "body": notification.body}
            if notification
            else None,
            "worker_outcome": outcome,
        }

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"initiative-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(f"\nResultado salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
