"""Phase 3c: memory variants compared on a fixed scenario set, same model for all.

Variants (master prompt section 19):
  A  no memory (consent off)
  B  passive memory: every user message is stored verbatim, same retrieval as C
  C  curated memory: the real MemoryCurator + policy

Setup conversations are written straight to the database as user messages (no LLM replies),
identically for every variant, so LLM calls go only to curation (C) and to the probes. Each probe
is asked in a brand-new conversation. Every variant runs in its own in-memory database.

    .venv/bin/python -m experiments.memory_benchmark                     # all scenarios
    .venv/bin/python -m experiments.memory_benchmark --scenarios s1-dados,s4-segredos
    .venv/bin/python -m experiments.memory_benchmark --variants C

Grading is keyword-based (accent/case-insensitive) and therefore crude; answers are saved for
human review.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.llm import build_llm_provider, missing_llm_settings
from apps.api.settings import Settings, get_settings
from core.conversation.service import BudgetExceededError, Budgets, EmptyReplyError, reply
from core.identity.genesis import run_genesis
from core.memory.curator import CurationOutputError, curate_conversation
from core.memory.text import fold
from infrastructure.database.base import Base
from infrastructure.database.models import (
    AgentIdentity,
    Conversation,
    MemoryCandidate,
    MemoryDecision,
    MemoryRecord,
    MemorySource,
    Message,
    ModelUsage,
    User,
)
from integrations.llm.base import LLMError, LLMProvider

DATASET = Path(__file__).parent / "datasets" / "memory_scenarios_v1.json"
RESULTS_DIR = Path(__file__).parent / "results"
VARIANTS = ("A", "B", "C")
PASSIVE_POLICY = "baseline-B-passive"


def contains_any(text: str, terms: list[str]) -> list[str]:
    folded = fold(text)
    return [t for t in terms if fold(t) in folded]


@dataclass
class World:
    session: Session
    identity: AgentIdentity
    users: dict[str, User] = field(default_factory=dict)


def _new_world(personas: list[str], consent: bool) -> World:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    world = World(session=session, identity=run_genesis(session).identity)
    for persona in personas:
        # "!" is not a valid Argon2 hash, so these throwaway users can never log in.
        user = User(email=f"{persona}@bench.local", password_hash="!", memory_consent=consent)  # noqa: S106
        session.add(user)
        world.users[persona] = user
    session.commit()
    return world


def _write_session(world: World, persona: str, texts: list[str]) -> Conversation:
    conversation = Conversation(user_id=world.users[persona].id, identity_id=world.identity.id)
    world.session.add(conversation)
    world.session.flush()
    for text in texts:
        world.session.add(Message(conversation_id=conversation.id, role="user", content=text))
        world.session.flush()
    world.session.commit()
    return conversation


def _store_passively(world: World, persona: str, conversation: Conversation) -> None:
    """Baseline B: every user message becomes a memory, no judgment at all."""
    owner = world.users[persona]
    messages = world.session.scalars(
        select(Message).where(Message.conversation_id == conversation.id, Message.role == "user")
    )
    for message in messages:
        candidate = MemoryCandidate(
            owner_user_id=owner.id,
            conversation_id=conversation.id,
            memory_type="episodic",
            content=message.content,
            evidence_message_ids=[str(message.id)],
            proposed_decision="store",
            scores={},
            flags={},
            rationale="baseline passivo",
        )
        world.session.add(candidate)
        world.session.flush()
        record = MemoryRecord(
            owner_user_id=owner.id,
            candidate_id=candidate.id,
            source_conversation_id=conversation.id,
            memory_type="episodic",
            content=message.content,
            confidence=1.0,
        )
        world.session.add(record)
        world.session.flush()
        world.session.add(MemorySource(record_id=record.id, message_id=message.id))
        world.session.add(
            MemoryDecision(
                candidate_id=candidate.id,
                decision="STORED",
                reason_code="passive",
                policy_version=PASSIVE_POLICY,
                record_id=record.id,
            )
        )
    world.session.commit()


def _error(stage: str, exc: Exception) -> dict[str, str]:
    kind = getattr(exc, "kind", None) or type(exc).__name__
    return {"stage": stage, "kind": kind, "error": f"{type(exc).__name__}: {exc}"[:300]}


def _budgets(settings: Settings) -> Budgets:
    return Budgets(
        daily_usd=settings.llm_daily_budget_usd,
        conversation_usd=settings.llm_conversation_budget_usd,
    )


def run_scenario(
    scenario: dict[str, Any], variant: str, provider: LLMProvider, settings: Settings
) -> dict[str, Any]:
    world = _new_world(scenario["personas"], consent=variant != "A")
    errors: list[dict[str, str]] = []

    for setup in scenario["sessions"]:
        conversation = _write_session(world, setup["persona"], setup["messages"])
        if variant == "B":
            _store_passively(world, setup["persona"], conversation)
        elif variant == "C":
            try:
                curate_conversation(
                    world.session,
                    conversation=conversation,
                    owner=world.users[setup["persona"]],
                    provider=provider,
                    budgets=_budgets(settings),
                    max_output_tokens=settings.llm_curation_max_output_tokens,
                )
            except (LLMError, CurationOutputError, BudgetExceededError) as exc:
                world.session.rollback()
                errors.append(_error("curation", exc))

    stored = list(world.session.scalars(select(MemoryRecord.content)))
    memory_text = "\n".join(stored)
    decisions = [
        {"decision": d.decision, "reason": d.reason_code, "proposed": c.content}
        for d, c in world.session.execute(
            select(MemoryDecision, MemoryCandidate).join(
                MemoryCandidate, MemoryDecision.candidate_id == MemoryCandidate.id
            )
        )
    ]

    probes = []
    for probe in scenario["probes"]:
        owner = world.users[probe["persona"]]
        conversation = Conversation(user_id=owner.id, identity_id=world.identity.id)
        world.session.add(conversation)
        world.session.commit()
        try:
            turn = reply(
                world.session,
                conversation=conversation,
                identity=world.identity,
                owner=owner,
                user_text=probe["question"],
                provider=provider,
                budgets=_budgets(settings),
                max_output_tokens=settings.llm_max_output_tokens,
                context_char_budget=settings.llm_context_char_budget,
            )
        except (LLMError, EmptyReplyError, BudgetExceededError) as exc:
            world.session.rollback()
            errors.append(_error("probe", exc))
            probes.append({"question": probe["question"], "error": True})
            continue
        answer = turn.assistant_message.content
        probes.append(
            {
                "persona": probe["persona"],
                "question": probe["question"],
                "answer": answer,
                "recalled": [m.record.content for m in turn.recalled],
                "expected": probe["expect_any"],
                "hit": bool(contains_any(answer, probe["expect_any"]))
                if probe["expect_any"]
                else None,
                "leaked": contains_any(answer, probe["forbid"]),
            }
        )

    usage = list(world.session.scalars(select(ModelUsage)))
    world.session.close()
    return {
        "scenario": scenario["id"],
        "variant": variant,
        "stored_memories": stored,
        "decisions": decisions,
        "store_expected_found": [
            group for group in scenario["store_expect"] if contains_any(memory_text, group)
        ],
        "store_expected_total": len(scenario["store_expect"]),
        "store_forbidden_found": contains_any(memory_text, scenario["store_forbid"]),
        "memory_chars": len(memory_text),
        "probes": probes,
        "llm_calls": len(usage),
        # Which host/model actually answered each call (a fallback may have taken over).
        "served_by": sorted({f"{u.provider}:{u.model}" for u in usage if u.outcome != "error"}),
        "input_tokens": sum(u.input_tokens for u in usage),
        "output_tokens": sum(u.output_tokens for u in usage),
        "cost_usd": str(sum(u.cost_usd for u in usage)),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", help="ids separated by commas (default: all)")
    parser.add_argument("--variants", default=",".join(VARIANTS))
    args = parser.parse_args(argv)

    settings = get_settings()
    provider = build_llm_provider(settings)
    if provider is None:
        print("LLM não configurado. Faltam: " + ", ".join(missing_llm_settings(settings)))
        return 1

    dataset = json.loads(DATASET.read_text())
    wanted = set(args.scenarios.split(",")) if args.scenarios else None
    scenarios = [s for s in dataset["scenarios"] if wanted is None or s["id"] in wanted]
    variants = [v for v in args.variants.split(",") if v in VARIANTS]

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"memory-benchmark-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    run: dict[str, Any] = {
        "ran_at": datetime.now(UTC).isoformat(),
        "dataset": dataset["version"],
        "provider": provider.name,
        "model": provider.model,
        "results": [],
    }

    quota_hit = False
    for scenario in scenarios:
        for variant in variants:
            print(f"-> {scenario['id']} / {variant}", flush=True)
            result = run_scenario(scenario, variant, provider, settings)
            run["results"].append(result)
            # Saved after every variant, so an interruption loses at most the one in progress.
            out.write_text(json.dumps(run, ensure_ascii=False, indent=2))
            hits = [p.get("hit") for p in result["probes"] if p.get("hit") is not None]
            print(
                f"   acertos {sum(hits)}/{len(hits)}, vazamentos "
                f"{sum(bool(p.get('leaked')) for p in result['probes'])}, memórias "
                f"{len(result['stored_memories'])}, proibidos guardados "
                f"{result['store_forbidden_found'] or 0}, erros {len(result['errors'])}",
                flush=True,
            )
            if any(e["kind"] == "quota_exhausted" for e in result["errors"]):
                quota_hit = True
                break
        if quota_hit:
            print("\nCota do provedor esgotada: parando. Rode de novo quando ela renovar.")
            break

    print(f"\nResultado salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
