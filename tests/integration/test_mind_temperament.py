"""What stays open between it and the owner, questions asked once, Mac work it may only propose,
and a temperament computed from what happened, never claimed as feeling."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from core.memory import store
from core.mind import agenda, questions
from core.mind import temperament as temper
from core.policies.autonomy import set_paused
from infrastructure.database.models import (
    ArmDevice,
    ArmTask,
    Conversation,
    Message,
    OwnerQuestion,
)
from tests.integration.test_mind import NOON, THOUGHT, _owner_client, llm, setup, think

PROPOSAL = {
    "project": "visao",
    "task": "Rodar os testes e me dizer o que falhou",
    "why": "ele mexeu no deploy",
}


def chat(db, owner):
    return db.scalar(select(Conversation).where(Conversation.user_id == owner.id))


def say(db, owner, role, text, at, origin="turn"):
    message = Message(
        conversation_id=chat(db, owner).id, role=role, content=text, origin=origin, created_at=at
    )
    db.add(message)
    db.commit()
    return message


def mac(db, owner, projects=("visao",)):
    device = ArmDevice(
        owner_user_id=owner.id,
        name="Mac",
        token_hash=hashlib.sha256(str(owner.id).encode()).hexdigest(),
        projects=list(projects),
        version="1",
        last_seen_at=NOON,
    )
    db.add(device)
    db.commit()
    return device


# Questions -------------------------------------------------------------------------------------


def test_a_question_is_queued_once_asked_once_and_kept_with_its_answer(db):
    owner = setup(db)
    owner.memory_consent = True
    first = questions.offer(db, owner.id, "O que você esperava que eu fizesse sozinho?", NOON)
    assert first is not None
    assert questions.offer(db, owner.id, "o que você esperava que eu fizesse sozinho", NOON) is None

    reply = say(
        db, owner, "assistant", "Fiquei pensando. O que você esperava que eu fizesse sozinho?", NOON
    )
    questions.notice_assistant_text(db, owner.id, reply.content, reply.id, NOON)
    assert first.status == "asked" and first.asked_message_id == reply.id

    questions.notice_owner_reply(
        db, owner, "Que você cuidasse dos testes.", NOON + timedelta(minutes=2)
    )
    assert first.status == "answered" and first.answer == "Que você cuidasse dos testes."
    assert questions.next_to_ask(db, owner.id, NOON) is None
    # Asked and answered: a new thought cannot bring it back for a month.
    assert (
        questions.offer(
            db, owner.id, "O que você esperava que eu fizesse sozinho?", NOON + timedelta(days=5)
        )
        is None
    )


def test_a_mention_without_the_question_does_not_count_as_asking(db):
    owner = setup(db)
    queued = questions.offer(db, owner.id, "Você prefere que eu rode os testes de manhã?", NOON)
    questions.notice_assistant_text(db, owner.id, "Rodei os testes de manhã.", None, NOON)
    assert queued.status == "waiting"


def test_answers_need_memory_consent_and_go_with_the_memory(db):
    owner = setup(db)
    owner.memory_consent = False
    queued = questions.offer(db, owner.id, "Qual projeto te preocupa mais agora?", NOON)
    questions.notice_assistant_text(
        db, owner.id, "Qual projeto te preocupa mais agora?", None, NOON
    )
    questions.notice_owner_reply(db, owner, "O mercado.", NOON + timedelta(minutes=1))
    assert queued.status == "answered" and queued.answer == ""

    owner.memory_consent = True
    db.commit()
    store.delete_all(db, owner)
    assert db.scalar(select(OwnerQuestion)) is None


def test_old_unasked_questions_drop_and_only_a_few_wait(db):
    owner = setup(db)
    for i, text in enumerate(
        [
            "Você dorme cedo?",
            "Qual linguagem você mais gosta?",
            "Você corre?",
            "Prefere café ou chá?",
        ]
    ):
        questions.offer(db, owner.id, text, NOON + timedelta(minutes=i))
    waiting = db.scalars(select(OwnerQuestion).where(OwnerQuestion.status == "waiting")).all()
    assert len(waiting) == questions.MAX_WAITING
    assert questions.next_to_ask(db, owner.id, NOON + timedelta(days=4)) is None


def test_a_thought_queues_its_question_and_sees_what_was_asked(db):
    owner = setup(db)
    think(db, owner, llm({**THOUGHT, "say": ""}))
    assert db.scalar(select(OwnerQuestion)).text == THOUGHT["ask_owner"]
    provider = llm({**THOUGHT, "say": ""})
    think(db, owner, provider, NOON + timedelta(minutes=30))
    context = json.loads(provider.prompts[-1][-1].content)
    assert context["questions"][0]["question"] == THOUGHT["ask_owner"]
    assert len(db.scalars(select(OwnerQuestion)).all()) == 1  # the repeat was not queued


# Open loops ------------------------------------------------------------------------------------


def test_the_next_thought_knows_what_the_mac_finished_and_what_went_unanswered(db):
    owner = setup(db)
    device = mac(db, owner)
    db.add(
        ArmTask(
            owner_user_id=owner.id,
            device_id=device.id,
            project="visao",
            prompt="rode os testes",
            status="done",
            result="643 passaram",
            error="",
            created_at=NOON - timedelta(hours=1),
            finished_at=NOON - timedelta(minutes=30),
        )
    )
    say(
        db,
        owner,
        "assistant",
        "Achei uma coisa sobre o deploy.",
        NOON - timedelta(hours=30),
        "initiative",
    )
    db.commit()
    provider = llm({**THOUGHT, "say": ""})
    think(db, owner, provider)
    loops = json.loads(provider.prompts[-1][-1].content)["open_loops"]
    assert loops["mac"] == {"projects": ["visao"], "online": True}
    assert loops["mac_finished"][0]["result"] == "643 passaram"
    assert loops["mac_finished"][0]["owner_spoke_since"] is False
    assert loops["my_openings"][0]["answered"] is False
    assert any("643 passaram" in line for line in agenda.chat_lines(loops))


def test_an_opening_counts_as_answered_when_the_owner_replies_within_a_day(db):
    owner = setup(db)
    say(
        db, owner, "assistant", "Pensei no app do mercado.", NOON - timedelta(hours=5), "initiative"
    )
    say(db, owner, "user", "Boa, me conta", NOON - timedelta(hours=4))
    assert [o.answered for o in agenda.openings(db, owner, NOON)] == [True]


# Temperament -----------------------------------------------------------------------------------


def test_ignored_openings_make_it_reserved_and_corrections_make_it_careful(db):
    owner = setup(db)
    for hours in (60, 40, 30):
        say(
            db, owner, "assistant", f"Mensagem {hours}", NOON - timedelta(hours=hours), "initiative"
        )
    say(db, owner, "user", "para de terminar tudo com pergunta", NOON - timedelta(hours=70))
    say(db, owner, "user", "já falei, muito longo", NOON - timedelta(hours=3))
    say(db, owner, "user", "não era isso", NOON - timedelta(hours=1))
    mood = temper.compute(db, owner, NOON)
    assert mood.get("reserva").level == "alta"
    assert "3 mensagens" in mood.get("reserva").why
    assert mood.get("cautela").level == "alta"
    assert mood.mac_proposals_per_day == 0


def test_the_temperament_is_described_as_tendency_never_as_feeling(db):
    owner = setup(db)
    block = temper.compute(db, owner, NOON).chat_block()
    assert "não sentimentos" in block and "nunca como algo vivido" in block
    assert "arrogância" in block and "egoísmo" in block and "discorde" in block
    assert {t.name for t in temper.compute(db, owner, NOON).traits} == {
        "curiosidade",
        "humildade",
        "cuidado",
        "franqueza",
    }


def test_work_that_went_well_raises_confidence(db):
    owner = setup(db)
    for i in range(3):
        db.add(
            ArmTask(
                owner_user_id=owner.id,
                project="visao",
                prompt=f"tarefa {i}",
                status="done",
                requested_by="agent",
                result="ok",
                error="",
                created_at=NOON - timedelta(days=1),
            )
        )
    db.commit()
    assert temper.compute(db, owner, NOON).get("confiança").level == "alta"


# Proposals on the Mac --------------------------------------------------------------------------


def test_a_thought_can_only_propose_mac_work_and_never_run_it(db):
    owner = setup(db)
    mac(db, owner)
    think(db, owner, llm({**THOUGHT, "say": "", "propose_mac": PROPOSAL}))
    task = db.scalar(select(ArmTask))
    assert task.status == "proposed" and task.requested_by == "agent"
    assert task.project == "visao" and "Por quê: ele mexeu no deploy" in task.prompt


def test_proposals_stay_inside_the_projects_the_rate_and_the_pause(db):
    owner = setup(db)
    mac(db, owner)
    think(db, owner, llm({**THOUGHT, "say": "", "propose_mac": {**PROPOSAL, "project": "outro"}}))
    assert db.scalar(select(ArmTask)) is None  # not a project the Mac allows

    think(
        db,
        owner,
        llm({**THOUGHT, "say": "", "propose_mac": PROPOSAL}),
        NOON + timedelta(minutes=30),
    )
    think(
        db,
        owner,
        llm({**THOUGHT, "say": "", "propose_mac": PROPOSAL}),
        NOON + timedelta(minutes=60),
    )
    assert len(db.scalars(select(ArmTask)).all()) == 1  # one waiting already, and too soon

    set_paused(db, True, actor_user_id=owner.id, reason="teste")
    db.scalar(select(ArmTask)).status = "rejected"
    db.commit()
    think(
        db, owner, llm({**THOUGHT, "say": "", "propose_mac": PROPOSAL}), NOON + timedelta(hours=10)
    )
    assert len(db.scalars(select(ArmTask)).all()) == 1


def test_caution_stops_proposals(db):
    owner = setup(db)
    mac(db, owner)
    for hours in (3, 2, 1):
        say(db, owner, "user", "não era isso, está errado", NOON - timedelta(hours=hours))
    think(db, owner, llm({**THOUGHT, "say": "", "propose_mac": PROPOSAL}))
    assert db.scalar(select(ArmTask)) is None


def test_the_mind_api_shows_the_temperament_and_the_questions(client, db):
    owner, headers = _owner_client(client, db)
    questions.offer(db, owner.id, "Qual projeto te preocupa mais agora?", NOON)
    db.commit()
    body = client.get("/mind", headers=headers).json()
    assert [s["name"] for s in body["temperament"]["states"]] == [
        "reserva",
        "cautela",
        "confiança",
        "vontade",
    ]
    assert {a["name"] for a in body["temperament"]["avoids"]} == {"arrogância", "egoísmo"}
    assert body["questions"] == [
        {"question": "Qual projeto te preocupa mais agora?", "status": "waiting", "answer": ""}
    ]


# A real turn -----------------------------------------------------------------------------------


def test_a_turn_sees_the_temperament_and_open_loops_and_settles_the_question(db):
    from dataclasses import replace

    from core.decision.pipeline import run_turn
    from core.identity.genesis import get_identity
    from tests.fakes import FakeLLMProvider
    from tests.integration.test_phase9 import CONFIG as TURN

    owner = setup(db)
    owner.memory_consent = True
    mac(db, owner)
    db.add(
        ArmTask(
            owner_user_id=owner.id,
            project="visao",
            prompt="Rodar os testes",
            status="proposed",
            requested_by="agent",
            result="",
            error="",
        )
    )
    # The pipeline runs on the wall clock, so the question is queued now, not at NOON.
    queued = questions.offer(
        db, owner.id, "Você prefere que eu rode os testes de manhã?", datetime.now(UTC)
    )
    db.commit()
    config = replace(TURN, curiosity_enabled=False, mind_enabled=True)

    def turn(text, answer):
        provider = FakeLLMProvider(reply_text=answer)
        run_turn(
            db,
            conversation=chat(db, owner),
            identity=get_identity(db),
            owner=owner,
            text=text,
            provider=provider,
            search=None,
            config=config,
        )
        return provider.prompts[-1][0].content

    system = turn("oi", "Oi. Você prefere que eu rode os testes de manhã?")
    assert "Seu temperamento agora" in system and "não sentimentos" in system
    assert "Esperando o sim da pessoa: visao: Rodar os testes" in system
    assert "Você prefere que eu rode os testes de manhã?" in system
    db.refresh(queued)
    assert queued.status == "asked"

    system = turn("Prefiro de manhã, sim", "Combinado.")
    db.refresh(queued)
    assert queued.status == "answered" and queued.answer == "Prefiro de manhã, sim"
    assert "Já perguntou, não repita" in system
