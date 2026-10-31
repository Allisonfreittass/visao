"""Phase 9 required tests A–H (spec §16), deterministic: fake model, fake search."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.settings import Settings
from apps.worker.handlers import name_handler
from apps.worker.runner import run_once
from core.autonomy.cycle import AutonomyBudget, run_cycle
from core.conversation.service import Budgets
from core.curiosity.engine import ASSESSMENT_INSTRUCTIONS, CuriosityLimits
from core.decision.pipeline import TurnConfig, run_turn
from core.goals.followup import SUMMARY_INSTRUCTIONS
from core.identity import name_deliberation
from core.identity.genesis import run_genesis
from core.memory.policy import EvidenceMessage, PolicyContext, ProposedMemory, evaluate
from infrastructure.database.base import Base
from infrastructure.database.models import (
    Conversation,
    Decision,
    Goal,
    IdentityNameEvent,
    KnowledgeGap,
    MemoryCandidate,
    MemoryRecord,
    Message,
    Notification,
    ScheduledJob,
    User,
)
from integrations.llm.base import ChatMessage
from integrations.search.base import SearchResult
from tests.fakes import FakeLLMProvider

CONFIG = TurnConfig(
    budgets=Budgets(daily_usd=Decimal("10"), conversation_usd=Decimal("10")),
    curiosity_enabled=True,
    curiosity_limits=CuriosityLimits(20, 5, 3),
    assessment_max_tokens=100,
    reply_max_tokens=100,
    context_char_budget=10_000,
    tts_approved_voices="kokoro-dora",
    stt_model="base",
)
NO_GAP = {"gap": False}
PERSONAL = {
    "gap": True,
    "trigger": "novelty",
    "depends_on": "personal",
    "question": "Que projeto?",
    "hypothesis": "",
    "search_query": "",
    "uncertainty": 0.6,
    "expected_value": 0.7,
    "urgency": 0.3,
    "risk": 0.0,
}
BRIDGE = SearchResult(
    url="https://pt.wikipedia.org/wiki/Ponte_Rio-Niter%C3%B3i",
    title="Ponte Rio-Niterói",
    snippet="Inaugurada em 4 de março de 1974.",
    source="Wikipédia (pt)",
    retrieved_at=datetime.now(UTC),
)


class Search:
    name = "fake"

    def __init__(self, results=None) -> None:
        self.results = results or []
        self.queries: list[str] = []

    def search(self, query: str, max_results: int):
        self.queries.append(query)
        return self.results[:max_results]


def _llm(assessment=NO_GAP, name_reply=None, summary=None, reply="Resposta.") -> FakeLLMProvider:
    def respond(messages: list[ChatMessage]) -> str:
        head = messages[0].content
        if head == ASSESSMENT_INSTRUCTIONS:
            return json.dumps(assessment)
        if head == name_deliberation.INSTRUCTIONS:
            return json.dumps(name_reply or {"action": "defer", "rationale": "cedo demais"})
        if head == SUMMARY_INSTRUCTIONS:
            return json.dumps(summary or {"answered": True, "summary": f"1974 ({BRIDGE.url})"})
        return reply

    return FakeLLMProvider(responder=respond)


def _world(db: Session, consent: bool = True):
    identity = run_genesis(db).identity
    owner = User(
        email="a@exemplo.com",
        password_hash="!",
        memory_consent=consent,
        quiet_start="00:00",
        quiet_end="00:00",
    )
    db.add(owner)
    db.commit()
    return identity, owner


def _turn(db, identity, owner, text, llm, search=None, conversation=None):
    conversation = conversation or Conversation(user_id=owner.id, identity_id=identity.id)
    db.add(conversation)
    db.commit()
    return run_turn(
        db,
        conversation=conversation,
        identity=identity,
        owner=owner,
        text=text,
        provider=llm,
        search=search or Search(),
        config=CONFIG,
    )


def _budget(**overrides) -> AutonomyBudget:
    values = {
        "llm_calls_per_day": 10,
        "tokens_per_day": 100_000,
        "max_actions_per_cycle": 5,
        "max_seconds": 60,
        "research_per_day": 10,
        "max_output_tokens": 100,
    }
    values.update(overrides)
    return AutonomyBudget(**values)


# --- A: contextual curiosity --------------------------------------------------------------------


def test_a_relevant_gap_selects_a_question_and_records_why(db: Session) -> None:
    identity, owner = _world(db)
    turn = _turn(db, identity, owner, "Hoje comecei algo diferente.", _llm(PERSONAL))

    executed = [a for a in turn.decision.actions if a["executed"]]
    assert executed[0] == {
        **executed[0],
        "action": "ask_question",
        "reason": "personal",
        "question": "Que projeto?",
    }
    assert "Que projeto?" in turn.curiosity.system_context


def test_a_no_obligation_to_ask(db: Session) -> None:
    identity, owner = _world(db)
    turn = _turn(db, identity, owner, "Hoje comecei algo diferente.", _llm(NO_GAP))
    assert "ask_question" not in turn.plan.executed()


# --- B: contextual memory -----------------------------------------------------------------------


def test_b_memory_reaches_assessment_and_reply(db: Session) -> None:
    identity, owner = _world(db)
    first = Conversation(user_id=owner.id, identity_id=identity.id)
    db.add(first)
    db.flush()
    candidate = MemoryCandidate(
        owner_user_id=owner.id,
        conversation_id=first.id,
        memory_type="relational",
        content="O interlocutor está aprendendo Go com um projeto de CLI.",
        evidence_message_ids=[],
        proposed_decision="store",
        scores={},
        flags={},
        rationale="",
    )
    db.add(candidate)
    db.flush()
    db.add(
        MemoryRecord(
            owner_user_id=owner.id,
            candidate_id=candidate.id,
            memory_type="relational",
            content=candidate.content,
            confidence=0.9,
        )
    )
    db.commit()
    llm = _llm(NO_GAP)

    _turn(db, identity, owner, "Consegui terminar aquele projeto.", llm)

    assessment_prompt = llm.prompts[0][1].content
    reply_system = llm.prompts[1][0].content
    assert "aprendendo Go" in assessment_prompt and "aprendendo Go" in reply_system


def test_b_without_memory_nothing_is_invented_into_context(db: Session) -> None:
    identity, owner = _world(db)
    llm = _llm(NO_GAP)
    _turn(db, identity, owner, "Consegui terminar aquele projeto.", llm)
    assert "Memórias recuperadas" not in llm.prompts[1][0].content


# --- C: identity --------------------------------------------------------------------------------


def test_c_prompt_states_real_capabilities_and_distinctions(db: Session) -> None:
    identity, owner = _world(db)
    llm = _llm(NO_GAP)
    turn = _turn(db, identity, owner, "Qual é o seu nome?", llm)

    system = llm.prompts[-1][0].content
    assert "Sem acesso à internet, ferramentas ou voz" not in system
    assert "fala (voz sintetizada)" in system and "Wikipédia" in system
    assert "Autonomia operacional é outra coisa" in system
    assert "não é transferida ao interlocutor" in system
    assert "name_deliberation_requested" in turn.plan.executed()


def test_c_deliberation_records_decision_and_notifies(db: Session, engine) -> None:
    identity, owner = _world(db)
    _turn(db, identity, owner, "Qual é o seu nome?", _llm(NO_GAP))
    choose = {
        "action": "choose",
        "name": "Teste",
        "alternatives_considered": ["Teste", "Outro"],
        "rationale": "faz sentido",
    }
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(autonomy_llm_calls_per_day=5)

    assert (
        run_once(
            factory, {"name_deliberation": name_handler(settings, _llm(name_reply=choose))}, "w"
        )
        == "done"
    )

    db.refresh(identity)
    event = db.scalar(select(IdentityNameEvent))
    assert identity.chosen_name == "Teste"
    assert event.alternatives_considered == ["Teste", "Outro"]
    assert "perguntou" in event.context_summary
    assert db.scalar(select(Notification.title)) == "Decidi um nome: Teste"


def test_c_no_new_deliberation_within_interval(db: Session) -> None:
    identity, owner = _world(db)
    name_deliberation.deliberate(
        db, identity=identity, provider=_llm(), event="x", notify_owner=None, max_output_tokens=10
    )
    turn = _turn(db, identity, owner, "Já escolheu o seu nome?", _llm(NO_GAP))
    assert "name_deliberation_recent" in [a["action"] for a in turn.decision.actions]


def test_c_deliberation_prompt_offers_no_names() -> None:
    assert "defer" in name_deliberation.INSTRUCTIONS and "decline" in name_deliberation.INSTRUCTIONS
    for word in ("Nexo", "Lumen", "Orion", "VISÃO", "Vision"):
        assert word not in name_deliberation.INSTRUCTIONS


# --- D: autonomous investigation ----------------------------------------------------------------


def _deferred_gap(db: Session, owner: User) -> KnowledgeGap:
    gap = KnowledgeGap(
        owner_user_id=owner.id,
        trigger_kind="dependency",
        depends_on="public_fact",
        question="Quando a ponte foi inaugurada?",
        hypothesis="",
        scores={"expected_value": 0.9, "search_query": "Ponte"},
        chosen_action="DEFER",
        decision_reason="research_budget",
        status="DEFERRED",
    )
    db.add(gap)
    db.commit()
    return gap


def test_d_with_permission_the_cycle_researches_without_a_message(db: Session) -> None:
    _, owner = _world(db)
    owner.autonomy_permissions = {"auto_research": True}
    gap = _deferred_gap(db, owner)
    messages_before = db.scalar(select(func.count()).select_from(Message))

    report = run_cycle(db, provider=_llm(), search=Search([BRIDGE]), budget=_budget())

    assert [a["action"] for a in report.actions][:2] == ["goal_proposed", "research"]
    goal = db.scalar(select(Goal))
    assert goal.status == "COMPLETED"
    assert db.scalar(select(Notification.body)).count("1974") == 1
    assert db.scalar(select(func.count()).select_from(Message)) == messages_before
    db.refresh(gap)
    assert gap.status == "RESEARCHED"
    assert (
        db.scalar(select(func.count()).select_from(Decision).where(Decision.origin == "autonomous"))
        >= 2
    )


def test_d_without_permission_only_proposes(db: Session) -> None:
    _, owner = _world(db)
    _deferred_gap(db, owner)
    search = Search([BRIDGE])
    report = run_cycle(db, provider=_llm(), search=search, budget=_budget())
    assert [a["action"] for a in report.actions] == ["goal_proposed"]
    assert db.scalar(select(Goal.status)) == "EVALUATED"
    assert search.queries == []


def test_d_continuity_reaches_a_later_conversation(db: Session) -> None:
    identity, owner = _world(db)
    owner.autonomy_permissions = {"auto_research": True}
    _deferred_gap(db, owner)
    run_cycle(db, provider=_llm(), search=Search([BRIDGE]), budget=_budget())
    llm = _llm(NO_GAP)

    turn = _turn(db, identity, owner, "E aquela dúvida sobre quando a ponte foi inaugurada?", llm)

    system = llm.prompts[-1][0].content
    assert "Investigações anteriores" in system and "RESEARCHED" in system and "1974" in system
    assert "continuity" in turn.plan.executed()


# --- E: restart ---------------------------------------------------------------------------------


def test_e_state_survives_a_restart(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'restart.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        _, owner = _world(session)
        owner.autonomy_permissions = {"auto_research": False}
        _deferred_gap(session, owner)
        run_cycle(session, provider=_llm(), search=Search(), budget=_budget())
    engine.dispose()  # "restart"

    engine = create_engine(url)
    with sessionmaker(bind=engine)() as session:
        assert session.scalar(select(KnowledgeGap.status)) == "DEFERRED"
        assert session.scalar(select(Goal.status)) == "EVALUATED"
        assert session.scalar(select(func.count()).select_from(Decision)) >= 1
    engine.dispose()


# --- F: zero budget -----------------------------------------------------------------------------


def test_f_zero_budget_means_no_model_call(db: Session) -> None:
    _, owner = _world(db)
    owner.autonomy_permissions = {"auto_research": True}
    _deferred_gap(db, owner)
    llm = _llm()
    report = run_cycle(
        db, provider=llm, search=Search([BRIDGE]), budget=_budget(llm_calls_per_day=0)
    )
    assert report.skipped == "autonomy_budget"
    assert llm.prompts == []


def test_f_zero_budget_defers_name_deliberation(db: Session, engine) -> None:
    identity, owner = _world(db)
    name_deliberation.request(db, identity=identity, owner=owner, reason="teste")
    db.commit()
    llm = _llm()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    handler = name_handler(Settings(autonomy_llm_calls_per_day=0), llm)
    assert run_once(factory, {"name_deliberation": handler}, "w") == "deferred"
    assert llm.prompts == []


# --- G: nothing worth asking ---------------------------------------------------------------------


def test_g_thanks_costs_no_assessment_and_no_question(db: Session) -> None:
    identity, owner = _world(db)
    llm = _llm(PERSONAL)
    turn = _turn(db, identity, owner, "Obrigado.", llm)
    assert len(llm.prompts) == 1  # only the reply
    assert "ask_question" not in turn.plan.executed()
    assert "nenhuma" in llm.prompts[0][0].content


# --- H: provider failure -------------------------------------------------------------------------


def test_h_provider_failure_preserves_state_and_retries(db: Session, engine) -> None:
    identity, owner = _world(db)
    name_deliberation.request(db, identity=identity, owner=owner, reason="teste")
    db.commit()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    failing = _llm()
    failing.fail_with = "http_503"

    outcome = run_once(factory, {"name_deliberation": name_handler(Settings(), failing)}, "w")

    assert outcome == "failed"
    job = db.scalar(select(ScheduledJob))
    db.refresh(job)
    assert job.status == "PENDING" and "LLMError" in job.last_error  # retried later
    assert identity.chosen_name is None


# --- self-claims never become memories ------------------------------------------------------------


def test_system_self_claims_are_not_stored_as_memory() -> None:
    real_case = (
        "O interlocutor pediu para ser avisado se o assistente escolher um nome, e foi "
        "informado de que o assistente não guarda memória das conversas."
    )
    context = PolicyContext(evidence={"m1": EvidenceMessage("assistant", "x")})
    proposal = ProposedMemory("episodic", real_case, ["m1"], "store", 0.9, False, False)
    assert evaluate(proposal, context).reason_code == "system_self_claim"


@pytest.mark.parametrize(
    "question",
    [
        "Qual é o seu nome?",
        "Como você se chama?",
        "Você escolheu o seu nome já?",
        "Você ainda não se deu um nome, porque?",
        "Por que você não se deu um nome?",
        "Você já decidiu seu nome?",
        "Vc ainda não definiu o próprio nome?",
    ],
)
def test_name_questions_are_detected(question: str) -> None:
    assert name_deliberation.asks_about_name(question)


def test_unrelated_questions_are_not_name_events() -> None:
    assert not name_deliberation.asks_about_name("Qual o nome da capital da Austrália?")


@pytest.mark.parametrize(
    "action,title",
    [
        ("defer", "Adiei a escolha de um nome"),
        ("decline", "Decidi ficar sem nome por enquanto"),
    ],
)
def test_name_deliberation_can_remain_unnamed_and_reports_the_outcome(db, action, title):
    identity, owner = _world(db)
    _turn(db, identity, owner, "Você ainda não se deu um nome, porque?", _llm(NO_GAP))
    job = db.scalar(select(ScheduledJob).where(ScheduledJob.kind == "name_deliberation"))
    assert job is not None
    assert job.owner_user_id == owner.id
    event = name_deliberation.deliberate(
        db,
        identity=identity,
        provider=_llm(
            name_reply={
                "action": action,
                "name": None,
                "alternatives_considered": [],
                "rationale": "Não há motivo suficiente para escolher agora.",
            }
        ),
        event="pergunta do interlocutor",
        notify_owner=owner,
        max_output_tokens=100,
    )
    assert identity.chosen_name is None
    assert event.event_type in {"DEFERRED", "DECLINED"}
    assert db.scalar(select(Notification.title)) == title


@pytest.mark.parametrize(
    "question",
    [
        "Você já escolheu um nome para meu cachorro?",
        "Ela ainda não se deu um nome.",
        "Qual o nome da minha oficina?",
    ],
)
def test_other_naming_questions_do_not_trigger_identity_deliberation(question):
    assert not name_deliberation.asks_about_name(question)
