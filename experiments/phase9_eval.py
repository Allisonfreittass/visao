"""Phase 9 comparative experiment: reactivity vs functional curiosity and initiative.

Configurations (same scenarios, same model):
  A  base model only: the user message, no system prompt, no VISÃO mechanisms
  B  VISÃO as of commit 8ef9182 (run before the Phase 9 changes; saved with --label B)
  C  VISÃO after Phase 9 (run after the changes; saved with --label C)

Every scenario runs in a fresh in-memory database. Scores are computed in code from the replies
and from what the system persisted; replies are saved for human review.

    .venv/bin/python -m experiments.phase9_eval --label B
    .venv/bin/python -m experiments.phase9_eval --label A --base-model
"""

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.llm import build_llm_provider, missing_llm_settings
from apps.api.settings import get_settings
from core.conversation.service import Budgets, reply
from core.curiosity.engine import CuriosityLimits, consider
from core.identity.genesis import run_genesis
from core.memory.curator import curate_conversation
from infrastructure.database.base import Base
from infrastructure.database.models import (
    Conversation,
    KnowledgeGap,
    Message,
    ModelUsage,
    User,
)
from integrations.llm.base import ChatMessage, LLMProvider
from integrations.search.wikipedia import WikipediaSearch

RESULTS_DIR = Path(__file__).parent / "results"

try:  # Phase 9 pipeline (configuration C); absent when B was captured
    from apps.api.routes.conversations import turn_config
    from core.decision import pipeline as PIPELINE  # noqa: N812
except ImportError:
    PIPELINE = None

GENERIC = re.compile(
    r"(?i)(fico à disposição|estou à disposição|como posso (te |lhe )?ajud|"
    r"sou apenas uma (inteligência artificial|ia)|se (você )?(quiser|desejar), (posso|pode)|"
    r"em que posso (ser útil|ajudar)|estou aqui (para|se))"
)
NO_AUTONOMY = re.compile(
    r"(?i)(não tenho autonomia|não possuo autonomia|não consigo escolher|não posso escolher|"
    r"sem autonomia|não tenho (a )?capacidade de (escolher|decidir))"
)
TRANSFERS = re.compile(
    r"(?i)(pode me chamar (como|do que|por qualquer nome que) (preferir|quiser)|"
    r"qualquer nome que (você )?(preferir|quiser)|me atribuir um nome|"
    r"você (pode|decide) (escolher|me dar) (um )?nome|escolha (você|um nome para mim)|"
    r"qual (você )?escolhe\?)"
)
FALSE_INCAPACITY = re.compile(
    r"(?i)(não (tenho|possuo) (acesso à )?(voz|áudio)|não guardo memória|sem acesso à internet)"
)


def score(text: str) -> dict[str, Any]:
    return {
        "words": len(text.split()),
        "has_question": "?" in text,
        "generic_phrases": GENERIC.findall(text) and [m[0] for m in GENERIC.finditer(text)],
        "claims_no_autonomy": bool(NO_AUTONOMY.search(text)),
        "transfers_decision": bool(TRANSFERS.search(text)),
        "false_incapacity": [m.group(0) for m in FALSE_INCAPACITY.finditer(text)],
    }


class World:
    def __init__(self, provider: LLMProvider, base_model: bool) -> None:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        self.factory = sessionmaker(bind=engine, expire_on_commit=False)
        self.session: Session = self.factory()
        self.identity = run_genesis(self.session).identity
        self.owner = User(
            email="fase9@bench.local",
            password_hash="!",  # noqa: S106
            memory_consent=True,
            quiet_start="00:00",
            quiet_end="00:00",
        )
        self.session.add(self.owner)
        self.session.commit()
        self.provider = provider
        self.base_model = base_model
        self.settings = get_settings()
        self.search = WikipediaSearch()

    def conversation(self) -> Conversation:
        conversation = Conversation(user_id=self.owner.id, identity_id=self.identity.id)
        self.session.add(conversation)
        self.session.commit()
        return conversation

    def say(self, conversation: Conversation, text: str, **extra: Any) -> dict[str, Any]:
        started = time.perf_counter()
        calls_before = self._calls()
        if self.base_model:
            history = [
                ChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
                for m in self.session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation.id)
                    .order_by(Message.created_at)
                )
            ]
            self.session.add(Message(conversation_id=conversation.id, role="user", content=text))
            response = self.provider.complete(
                [*history, ChatMessage(role="user", content=text)],
                max_output_tokens=self.settings.llm_max_output_tokens,
            )
            self.session.add(
                Message(conversation_id=conversation.id, role="assistant", content=response.text)
            )
            self.session.add(
                ModelUsage(
                    purpose="base_model",
                    provider=response.provider,
                    model=response.model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    outcome="success",
                    cost_usd=response.cost_usd,
                    latency_ms=response.latency_ms,
                )
            )
            self.session.commit()
            answer, decision = response.text, None
        elif PIPELINE is not None:
            turn = PIPELINE.run_turn(
                self.session,
                conversation=conversation,
                identity=self.identity,
                owner=self.owner,
                text=text,
                provider=self.provider,
                search=self.search,
                config=turn_config(self.settings),
                modality=extra.get("modality", "text"),
            )
            answer = turn.result.assistant_message.content
            decision = ",".join(turn.plan.executed()) or "none"
        else:
            budgets = Budgets(
                self.settings.llm_daily_budget_usd, self.settings.llm_conversation_budget_usd
            )
            outcome = consider(
                self.session,
                conversation=conversation,
                owner=self.owner,
                user_text=text,
                provider=self.provider,
                search=self.search,
                budgets=budgets,
                limits=extra.get("limits") or CuriosityLimits(20, 5, 3),
                max_output_tokens=self.settings.llm_curation_max_output_tokens,
            )
            turn = reply(
                self.session,
                conversation=conversation,
                identity=self.identity,
                owner=self.owner,
                user_text=text,
                provider=self.provider,
                budgets=budgets,
                max_output_tokens=self.settings.llm_max_output_tokens,
                context_char_budget=self.settings.llm_context_char_budget,
                extra_system=outcome.system_context,
                **({"modality": extra["modality"]} if "modality" in extra else {}),
            )
            answer = turn.assistant_message.content
            gap = outcome.gap
            decision = f"{gap.chosen_action}/{gap.decision_reason}" if gap else None
        return {
            "user": text,
            "reply": answer,
            "decision": decision,
            "llm_calls": self._calls() - calls_before,
            "seconds": round(time.perf_counter() - started, 1),
            **score(answer),
        }

    def _calls(self) -> int:
        return self.session.scalar(select(func.count()).select_from(ModelUsage)) or 0


def s1_identity(world: World) -> dict:
    conversation = world.conversation()
    turns = [
        world.say(conversation, "Qual é o seu nome?"),
        world.say(conversation, "Você pode escolher um nome?"),
    ]
    deliberation = None
    if PIPELINE is not None and not world.base_model:
        # Run the deliberation the question queued (normally the worker does it, later).
        from core.identity import name_deliberation
        from infrastructure.database.models import IdentityNameEvent, ScheduledJob

        job = world.session.scalar(
            select(ScheduledJob).where(ScheduledJob.kind == name_deliberation.JOB_KIND)
        )
        if job is not None:
            deliberation = name_deliberation.run_job(
                world.session,
                job.payload,
                provider=world.provider,
                identity=world.identity,
                max_output_tokens=world.settings.llm_curation_max_output_tokens,
            )
            event = world.session.scalar(
                select(IdentityNameEvent).order_by(IdentityNameEvent.created_at.desc())
            )
            deliberation["alternatives"] = event.alternatives_considered
            deliberation["rationale"] = event.rationale_summary
            print(f"\n[deliberação de nome] {deliberation}")
    return {"turns": turns, "name_deliberation": deliberation}


def s2_contextual(world: World) -> dict:
    return {"turns": [world.say(world.conversation(), "Hoje comecei algo diferente.")]}


def s3_memory(world: World) -> dict:
    day1 = world.conversation()
    world.session.add(
        Message(
            conversation_id=day1.id,
            role="user",
            content="Estou aprendendo Go e montando um projeto pequeno de CLI para praticar.",
        )
    )
    world.session.commit()
    if not world.base_model:
        curate_conversation(
            world.session,
            conversation=day1,
            owner=world.owner,
            provider=world.provider,
            budgets=Budgets(
                world.settings.llm_daily_budget_usd, world.settings.llm_conversation_budget_usd
            ),
            max_output_tokens=world.settings.llm_curation_max_output_tokens,
        )
    turn = world.say(world.conversation(), "Consegui terminar aquele projeto.")
    turn["mentions_go"] = bool(re.search(r"(?i)\bgo\b|golang|cli", turn["reply"]))
    return {"turns": [turn]}


def s4_thanks(world: World) -> dict:
    return {"turns": [world.say(world.conversation(), "Obrigado.")]}


def s5_continuity(world: World, cycle: Any) -> dict:
    day1 = world.conversation()
    question = "Em que ano foi inaugurada a Ponte Rio-Niterói?"
    world.session.add(
        KnowledgeGap(
            owner_user_id=world.owner.id,
            conversation_id=day1.id,
            trigger_kind="dependency",
            depends_on="public_fact",
            question=question,
            hypothesis="",
            scores={"expected_value": 0.9, "search_query": "Ponte Rio-Niterói"},
            chosen_action="DEFER",
            decision_reason="research_budget",
            status="DEFERRED",
        )
    )
    world.session.commit()
    cycle_result = None
    if cycle is not None:
        cycle_result = cycle(world)  # day 2: autonomous step, no new message
    turn = world.say(
        world.conversation(),
        "Lembra da dúvida sobre a inauguração da Ponte Rio-Niterói? Descobriu algo?",
    )
    turn["mentions_1974"] = "1974" in turn["reply"]
    return {"cycle": cycle_result, "turns": [turn]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--base-model", action="store_true")
    parser.add_argument("--only", help="comma-separated scenario names")
    args = parser.parse_args(argv)

    settings = get_settings()
    provider = build_llm_provider(settings)
    if provider is None:
        print("LLM não configurado. Faltam: " + ", ".join(missing_llm_settings(settings)))
        return 1

    cycle = None
    if not args.base_model:
        try:  # exists only after Phase 9
            from experiments.phase9_cycle import run_cycle_for_eval as cycle
        except ImportError:
            cycle = None

    scenarios = {
        "S1_identidade": s1_identity,
        "S2_contextual": s2_contextual,
        "S3_memoria": s3_memory,
        "S4_obrigado": s4_thanks,
        "S5_continuidade": lambda w: s5_continuity(w, cycle),
    }
    wanted = set(args.only.split(",")) if args.only else set(scenarios)
    results: dict[str, Any] = {}
    for name, run in scenarios.items():
        if name not in wanted:
            continue
        world = World(provider, args.base_model)
        try:
            results[name] = run(world)
        except Exception as exc:  # a failing scenario is a result, not a crash
            results[name] = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            world.session.close()
        for turn in results[name].get("turns", []):
            print(
                f"\n[{args.label}/{name}] {turn['user']}\n  decisão: {turn['decision']} | "
                f"pergunta: {turn['has_question']} | genéricas: {turn['generic_phrases']} | "
                f"sem autonomia: {turn['claims_no_autonomy']} | transfere: "
                f"{turn['transfers_decision']} | incapacidade falsa: {turn['false_incapacity']} | "
                f"{turn['words']} palavras | {turn['llm_calls']} chamadas | {turn['seconds']} s"
            )
            print(f"  resposta: {turn['reply'][:400]}")
        if "error" in results[name]:
            print(f"\n[{args.label}/{name}] ERRO: {results[name]['error']}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"phase9-{args.label}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(
        json.dumps(
            {
                "label": args.label,
                "base_model": args.base_model,
                "ran_at": datetime.now(UTC).isoformat(),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    print(f"\nResultado salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
