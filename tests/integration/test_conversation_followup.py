"""Exercise actual turn -> persisted gap -> idle cycle -> owner notification."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from core.autonomy.cycle import run_cycle, usage_today
from core.initiatives.followup import INSTRUCTIONS
from core.policies.autonomy import set_paused
from infrastructure.database.models import Message, Notification
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


def test_idle_thread_sends_once_and_counts_autonomy_usage(db):
    owner, turn, now, llm = setup_thread(db)
    report = run_cycle(db, provider=llm, search=Search(), budget=_budget(), now=now)
    assert any(a["action"] == "conversation_followup" and a["executed"] for a in report.actions)
    notification = db.scalar(select(Notification))
    assert notification.owner_user_id == owner.id
    assert "Maré" in notification.body
    assert llm.prompts[0][0].content == INSTRUCTIONS
    assert turn.curiosity.gap.status == "FOLLOWUP_NOTIFIED"
    assert usage_today(db, now)[0] == 1
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
        owner.timezone, owner.quiet_start, owner.quiet_end = "UTC", "00:00", "23:59"
        now = now.replace(hour=12)
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
    from infrastructure.database.models import ScheduledJob

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
