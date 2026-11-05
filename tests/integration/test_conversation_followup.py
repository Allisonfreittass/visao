"""Exercise actual turn -> persisted gap -> idle cycle -> owner notification."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from core.autonomy.cycle import run_cycle, usage_today
from core.identity.genesis import get_identity
from core.initiatives.followup import INSTRUCTIONS, PURPOSE
from core.policies.autonomy import set_paused
from infrastructure.database.models import (
    Conversation,
    KnowledgeGap,
    Message,
    ModelUsage,
    Notification,
    ScheduledJob,
)
from tests.fakes import FakeLLMProvider
from tests.integration.test_phase9 import Search, _budget, _llm, _turn, _world

THREAD = {
    "gap": True,
    "trigger": "dependency",
    "depends_on": "conversation",
    "question": "Como localizar os livros da biblioteca Maré?",
    "expected_value": 0.8,
    "risk": 0.0,
}


def setup_thread(db):
    identity, owner = _world(db)
    turn = _turn(db, identity, owner, "Deixamos em aberto como localizar os livros.", _llm(THREAD))
    assert turn.curiosity.gap.status == "DEFERRED"
    assert turn.curiosity.proposed_goal is None  # no web task or approval needed
    assert "research_deferred" not in turn.plan.executed()
    assert "conversation_thread_detected" in turn.plan.executed()
    assert "conversation_followup_scheduled" in turn.plan.executed()
    now = datetime.now(UTC) + timedelta(minutes=11)
    llm = FakeLLMProvider(
        reply_text=json.dumps(
            {
                "send": True,
                "body": "Na biblioteca Maré, como o leitor encontraria o livro deslocado?",
            }
        )
    )
    return owner, turn, now, llm


@pytest.mark.parametrize(
    "text",
    [
        "Terminei a tela de login do app ontem.",
        "Hoje vou mexer na parte de voz.",
        "Decidi tirar o Cloudflare do caminho por enquanto.",
        "Deixei a tela de perfil para depois.",
    ],
)
def test_statement_the_model_reads_as_pending_creates_no_thread(db, text):
    identity, owner = _world(db)
    turn = _turn(db, identity, owner, text, _llm(THREAD))
    gap = turn.curiosity.gap
    assert (gap.chosen_action, gap.decision_reason) == ("IGNORE", "not_left_open")
    assert gap.status == "IGNORED"
    assert "conversation_thread_detected" not in turn.plan.executed()
    assert "conversation_followup_scheduled" not in turn.plan.executed()
    assert db.scalar(select(ScheduledJob)) is None


def test_question_set_aside_after_it_was_raised_creates_a_thread(db):
    identity, owner = _world(db)
    first = _turn(db, identity, owner, "Não sei como localizar os livros.", _llm())
    conversation = db.get(Conversation, first.result.user_message.conversation_id)
    turn = _turn(
        db,
        identity,
        owner,
        "Vamos deixar isso para depois.",
        _llm(THREAD),
        conversation=conversation,
    )
    assert "conversation_thread_detected" in turn.plan.executed()


def _legacy_thread(db, owner):
    """A thread recorded by the old policy, which trusted the model alone."""
    conversation = Conversation(user_id=owner.id, identity_id=get_identity(db).id)
    db.add(conversation)
    db.flush()
    message = Message(conversation_id=conversation.id, role="user", content="Mexi na voz hoje.")
    db.add_all(
        [
            message,
            Message(conversation_id=conversation.id, role="assistant", content="Certo."),
        ]
    )
    db.flush()
    gap = KnowledgeGap(
        owner_user_id=owner.id,
        conversation_id=conversation.id,
        trigger_message_id=message.id,
        trigger_kind="dependency",
        depends_on="conversation",
        question="O que você vai implementar na voz?",
        hypothesis="",
        scores={"expected_value": 0.8, "policy_version": "2026-10-31.4"},
        chosen_action="DEFER",
        decision_reason="open_conversation_thread",
        status="DEFERRED",
    )
    db.add(gap)
    db.commit()
    return gap


def test_legacy_thread_never_notifies(db):
    _, owner = _world(db)
    gap = _legacy_thread(db, owner)
    llm = FakeLLMProvider(reply_text=json.dumps({"send": True, "body": "E a voz?"}))
    now = datetime.now(UTC) + timedelta(minutes=11)
    run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    assert not llm.prompts
    assert db.scalar(select(Notification)) is None
    assert gap.status == "FOLLOWUP_SKIPPED"
    assert gap.scores["followup"]["outcome"] == "not_left_open"


def test_continuity_hides_a_legacy_thread_but_keeps_a_real_one(db):
    identity, owner = _world(db)
    gap = _legacy_thread(db, owner)
    llm = _llm()
    turn = _turn(db, identity, owner, "O que vou implementar na voz hoje", llm)
    assert "continuity" not in turn.plan.executed()

    gap.scores = {**gap.scores, "left_open": True}
    db.commit()
    llm = _llm()
    turn = _turn(db, identity, owner, "O que vou implementar na voz hoje", llm)
    assert "continuity" in turn.plan.executed()
    assert "não anuncie uma pendência" in llm.prompts[-1][0].content


def test_idle_thread_sends_once_and_counts_autonomy_usage(db):
    owner, turn, now, llm = setup_thread(db)
    report = run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    assert any(a["action"] == "conversation_followup" and a["executed"] for a in report.actions)
    notification = db.scalar(select(Notification))
    assert notification.owner_user_id == owner.id
    assert "Maré" in notification.body
    assert llm.prompts[0][0].content == INSTRUCTIONS
    assert turn.curiosity.gap.status == "FOLLOWUP_NOTIFIED"
    # `now` is simulated, 11 minutes ahead, but rows carry the real clock: near midnight they fall
    # on different days. Asking about the row's own day holds at any hour.
    usage = db.scalar(select(ModelUsage).where(ModelUsage.purpose == PURPOSE))
    assert usage_today(db, usage.created_at)[0] == 1
    run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    assert len(db.scalars(select(Notification)).all()) == 1
    assert len(llm.prompts) == 1


@pytest.mark.parametrize("block", ["early", "paused", "quiet", "budget", "superseded"])
def test_blocked_thread_does_not_call_model_or_notify(db, block):
    owner, turn, now, llm = setup_thread(db)
    budget = _budget()
    if block == "early":
        now = datetime.now(UTC) + timedelta(minutes=2)
    elif block == "paused":
        set_paused(db, True, actor_user_id=owner.id, reason="teste")
    elif block == "quiet":
        # A window around `now`: moving `now` instead would depend on the hour the test runs.
        owner.timezone = "UTC"
        owner.quiet_start = f"{(now - timedelta(hours=1)):%H:%M}"
        owner.quiet_end = f"{(now + timedelta(hours=1)):%H:%M}"
        db.commit()
    elif block == "budget":
        budget = _budget(llm_calls_per_day=0)
    else:
        db.add(
            Message(
                conversation_id=turn.result.user_message.conversation_id,
                role="user",
                content="Mudei de assunto.",
            )
        )
        db.commit()
    run_cycle(db, provider=llm, search=Search(), budget=budget, now=now)
    assert not llm.prompts
    assert db.scalar(select(Notification)) is None


@pytest.mark.parametrize("reply", ['{"send": false, "body": ""}', "invalid json"])
def test_no_useful_invitation_or_bad_output_stays_quiet(db, reply):
    _, turn, now, llm = setup_thread(db)
    llm.reply_text = reply
    run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    assert db.scalar(select(Notification)) is None
    assert turn.curiosity.gap.status == "FOLLOWUP_SKIPPED"
    run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    assert len(llm.prompts) == 1


def test_user_activity_during_generation_cancels_invitation(db):
    _, turn, now, llm = setup_thread(db)

    def respond(messages):
        db.add(
            Message(
                conversation_id=turn.result.user_message.conversation_id,
                role="user",
                content="Já resolvi, vamos mudar de assunto.",
            )
        )
        db.commit()
        return json.dumps({"send": True, "body": "Uma pergunta que ficou obsoleta?"})

    llm.responder = respond
    run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    assert db.scalar(select(Notification)) is None


def test_scheduled_worker_delivers_without_another_user_turn(db, engine):
    from sqlalchemy.orm import sessionmaker

    from apps.api.settings import Settings
    from apps.worker.handlers import cycle_handler
    from apps.worker.runner import run_once

    _, turn, _, llm = setup_thread(db)
    job = db.scalar(select(ScheduledJob).where(ScheduledJob.kind == "cognitive_cycle"))
    assert job is not None
    assert job.payload["gap_id"] == str(turn.curiosity.gap.id)
    # Advance persisted time rather than waiting ten real minutes.
    old = datetime.now(UTC) - timedelta(minutes=11)
    for index, message in enumerate(
        db.scalars(select(Message).order_by(Message.created_at, Message.id))
    ):
        message.created_at = old + timedelta(seconds=index)
    job.run_after = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    outcome = run_once(
        factory, {"cognitive_cycle": cycle_handler(Settings(), llm, Search())}, "test"
    )
    assert outcome == "done"
    db.expire_all()
    assert db.scalar(select(Notification)) is not None


@pytest.mark.parametrize(
    ("reply", "outcome", "model_reason"),
    [
        (
            '{"send": false, "reason": "no_useful_question", "body": ""}',
            "model_declined",
            "no_useful_question",
        ),
        (
            '{"send": true, "reason": "useful_next_step", "body": ""}',
            "invalid_body",
            "useful_next_step",
        ),
        ('{"send": "true", "body": "Uma pergunta?"}', "invalid_output", "unspecified"),
        ("[]", "invalid_output", "unspecified"),
        ("invalid JSON", "invalid_output", "unspecified"),
        (
            '{"send": false, "reason": "texto livre não deve ser persistido", "body": ""}',
            "model_declined",
            "unspecified",
        ),
    ],
)
def test_skip_diagnostics_distinguish_model_refusal_and_invalid_output(
    db, reply, outcome, model_reason
):
    _, turn, now, llm = setup_thread(db)
    llm.reply_text = reply
    run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    diagnostic = turn.curiosity.gap.scores["followup"]
    assert diagnostic["outcome"] == outcome
    assert diagnostic["model_reason"] == model_reason
    assert diagnostic["idle_seconds"] >= 600
    assert db.scalar(select(Notification)) is None


def test_context_contains_elapsed_time_and_history_is_data(db):
    _, _, now, llm = setup_thread(db)
    run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    prompt = llm.prompts[0]
    assert [m.role for m in prompt] == ["system", "user"]
    context = json.loads(prompt[1].content)
    assert context["idle_seconds"] >= context["minimum_idle_seconds"] == 600
    assert context["exchange"][-1]["role"] == "assistant"


@pytest.mark.parametrize(
    ("failure", "outcome"),
    [
        ("truncated", "truncated_output"),
        ("provider", "provider_error"),
        ("paused", "paused_before_delivery"),
    ],
)
def test_generation_and_delivery_failures_are_distinct(db, failure, outcome):
    owner, turn, now, llm = setup_thread(db)
    if failure == "truncated":
        llm.finish_reason = "length"
    elif failure == "provider":
        llm.fail_with = "timeout"
    else:

        def respond(messages):
            set_paused(db, True, actor_user_id=owner.id, reason="durante geração")
            return json.dumps({"send": True, "body": "Uma pergunta?"})

        llm.responder = respond
    run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    assert turn.curiosity.gap.scores["followup"]["outcome"] == outcome
    assert db.scalar(select(Notification)) is None
