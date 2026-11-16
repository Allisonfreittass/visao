"""One continuous conversation, its past summarized in segments (docs/decisions/0014)."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core.conversation import segments
from core.decision import record
from core.identity.genesis import run_genesis
from infrastructure.database.models import (
    Conversation,
    ConversationSegment,
    Decision,
    Message,
    ScheduledJob,
    User,
)
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login

SUMMARY = {
    "title": "Viagem a Santiago",
    "summary": "A pessoa quer ir a Santiago em agosto, a dois, para esquiar; o assistente cotou "
    "voos saindo de Guarulhos.",
    "keywords": ["santiago", "esqui", "agosto"],
}
START = datetime(2026, 11, 10, 13, 0, tzinfo=UTC)


def llm_world(client, db, *, summary=SUMMARY, reply="resposta de teste"):
    def respond(messages):
        if messages[0].content == segments.INSTRUCTIONS:
            return json.dumps(summary)
        return reply

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm


def talk(db, conversation, lines, start=START, step=timedelta(minutes=2)):
    """Messages at given times: (role, text) pairs, `step` apart, from `start`."""
    made = []
    for n, (role, text) in enumerate(lines):
        message = Message(
            conversation_id=conversation.id, role=role, content=text, created_at=start + step * n
        )
        db.add(message)
        made.append(message)
    db.commit()
    return made


def _continuous(client, headers, db):
    data = client.get("/conversations/continuous", headers=headers).json()
    return data, db.get(Conversation, uuid.UUID(data["id"]))


def test_there_is_one_continuous_conversation_and_it_comes_first(client, db):
    llm_world(client, db)
    headers = _login(client, db)
    older = client.post("/conversations", headers=headers).json()

    first, _ = _continuous(client, headers, db)
    again, _ = _continuous(client, headers, db)

    assert first["continuous"] is True and first["id"] == again["id"]
    listed = client.get("/conversations", headers=headers).json()
    assert listed[0]["id"] == first["id"] and listed[1]["id"] == older["id"]
    assert listed[1]["continuous"] is False
    project = client.post("/projects", headers=headers, json={"name": "Viagem"}).json()
    moved = client.put(
        f"/conversations/{first['id']}/project", headers=headers, json={"project_id": project["id"]}
    )
    assert moved.status_code == 409


def test_a_segment_ends_at_a_long_pause_a_new_day_or_too_many_messages():
    zone = ZoneInfo("America/Sao_Paulo")

    def at(hours):
        return Message(role="user", content="x", created_at=START + timedelta(hours=hours))

    pieces = segments.chunks([at(0), at(1), at(5), at(5.5), at(14)], zone)
    # 13:00 and 14:00 UTC; 18:00 after a pause; 03:00 UTC next day is 00:00 in São Paulo.
    assert [len(p) for p in pieces] == [2, 2, 1]
    many = [at(n / 60) for n in range(segments.MAX_MESSAGES + 3)]
    assert [len(p) for p in segments.chunks(many, zone)] == [segments.MAX_MESSAGES, 3]


def test_the_worker_closes_and_summarizes_what_is_due(client, db):
    llm = llm_world(client, db)
    headers = _login(client, db)
    _, conversation = _continuous(client, headers, db)
    talk(
        db,
        conversation,
        [
            ("user", "quero ir a Santiago em agosto, a dois, para esquiar"),
            ("assistant", "Cotei voos saindo de Guarulhos."),
        ],
    )
    later = START + timedelta(hours=5)
    talk(db, conversation, [("user", "voltei, e o hotel?")], start=later)

    closed = segments.close_due(db, conversation, llm, lambda: True, now=later)

    assert closed == 1
    segment = db.scalar(select(ConversationSegment))
    assert (segment.status, segment.title, segment.messages) == ("summarized", SUMMARY["title"], 2)
    assert segment.keywords == ["santiago", "esqui", "agosto"]
    # The open stretch stays open: it is the one being talked about.
    assert segments.close_due(db, conversation, llm, lambda: True, now=later) == 0


def test_a_summary_that_adds_a_number_is_refused_and_the_messages_stay_raw(client, db):
    bad = {**SUMMARY, "summary": "A pessoa quer ir a Santiago em agosto, por R$ 9.999."}
    llm = llm_world(client, db, summary=bad)
    headers = _login(client, db)
    _, conversation = _continuous(client, headers, db)
    talk(db, conversation, [("user", "quero ir a Santiago em agosto"), ("assistant", "Boa.")])

    segments.close_due(db, conversation, llm, lambda: True, now=START + timedelta(days=1))

    segment = db.scalar(select(ConversationSegment))
    assert segment.status == "failed" and segment.summary == ""
    assert [m.content for m in segments.window(db, conversation)][0].startswith("quero ir")


def test_without_autonomy_room_nothing_is_called_and_the_segment_is_read_raw(client, db):
    llm = llm_world(client, db)
    headers = _login(client, db)
    _, conversation = _continuous(client, headers, db)
    talk(db, conversation, [("user", "oi"), ("assistant", "oi!")])
    segments.close_due(db, conversation, llm, lambda: False, now=START + timedelta(days=1))
    assert db.scalar(select(ConversationSegment)).status == "failed"
    assert all(p[0].content != segments.INSTRUCTIONS for p in llm.prompts)


def test_the_reply_reads_the_open_stretch_raw_and_the_past_as_summaries(client, db):
    told = {
        "title": "Viagem a Santiago",
        "summary": "A pessoa mandou várias mensagens antigas sobre santiago.",
        "keywords": ["santiago"],
    }
    llm = llm_world(client, db, summary=told)
    headers = _login(client, db)
    data, conversation = _continuous(client, headers, db)
    old = [("user", f"mensagem antiga {n} sobre santiago") for n in range(20)]
    talk(db, conversation, old)
    segments.close_due(db, conversation, llm, lambda: True, now=START + timedelta(days=1))

    turn = client.post(
        f"/conversations/{data['id']}/messages",
        headers=headers,
        json={"content": "e o esqui em Santiago, quanto custa a aula?"},
    )

    assert turn.status_code == 200
    asked = "e o esqui em Santiago, quanto custa a aula?"
    prompt = next(p for p in reversed(llm.prompts) if p[-1].content == asked)
    assert "Trechos anteriores desta conversa contínua" in prompt[0].content
    assert "Viagem a Santiago (10/11)" in prompt[0].content
    raw = [m.content for m in prompt[1:]]
    # The last few old messages still go raw (the thread just before); the oldest do not.
    assert "mensagem antiga 0 sobre santiago" not in raw
    assert "mensagem antiga 19 sobre santiago" in raw
    assert raw[-1] == "e o esqui em Santiago, quanto custa a aula?"
    # The turn queued the worker to close what is due.
    assert db.scalar(select(ScheduledJob).where(ScheduledJob.kind == segments.JOB_KIND))


def test_summaries_are_chosen_by_subject_and_more_when_asked_to_remember(client, db):
    llm_world(client, db)
    headers = _login(client, db)
    _, conversation = _continuous(client, headers, db)
    owner = db.scalar(select(User))
    for n, (title, words) in enumerate(
        [
            ("Viagem a Santiago", ["santiago", "esqui"]),
            ("Bug no login", ["login", "app"]),
            ("Receita de bolo", ["bolo", "receita"]),
            ("Mercado da semana", ["mercado"]),
        ]
    ):
        db.add(
            ConversationSegment(
                owner_user_id=owner.id,
                conversation_id=conversation.id,
                first_message_id=uuid.uuid4(),
                last_message_id=uuid.uuid4(),
                started_at=START + timedelta(days=n),
                ended_at=START + timedelta(days=n, hours=1),
                messages=4,
                title=title,
                summary=f"Resumo de {title}.",
                keywords=words,
                status="summarized",
            )
        )
    db.commit()

    picked = [s.title for s in segments.chosen(db, conversation, "e o esqui em santiago?", [])]
    # The latest stretch always (the thread just before), plus the one about the subject.
    assert picked == ["Viagem a Santiago", "Mercado da semana"]
    remember = segments.chosen(db, conversation, "lembra do bug no login do app?", [])
    assert "Bug no login" in [s.title for s in remember]


def test_the_record_of_deeds_covers_the_last_week_in_the_continuous_conversation(client, db):
    llm_world(client, db)
    headers = _login(client, db)
    _, conversation = _continuous(client, headers, db)
    owner = db.scalar(select(User))
    now = datetime.now(UTC)
    for when in (now - timedelta(days=10), now - timedelta(days=1)):
        message = Message(
            conversation_id=conversation.id, role="assistant", content="ok", created_at=when
        )
        db.add(message)
        db.flush()
        db.add(
            Decision(
                owner_user_id=owner.id,
                conversation_id=conversation.id,
                message_id=message.id,
                origin="turn",
                actions=[{"action": "research", "executed": True, "reason": "x", "sources": 1}],
                created_at=when,
            )
        )
    db.commit()

    lines = [
        ln
        for ln in record.conversation_block(db, conversation, owner).splitlines()
        if ln[:2] == "- "
    ]
    assert len(lines) == 1


def test_messages_load_backwards_in_pages(client, db):
    llm_world(client, db)
    headers = _login(client, db)
    data, conversation = _continuous(client, headers, db)
    made = talk(db, conversation, [("user", f"m{n}") for n in range(7)])
    base = f"/conversations/{data['id']}/messages"

    last = client.get(f"{base}?limit=3", headers=headers).json()
    before = client.get(f"{base}?limit=3&before={last[0]['id']}", headers=headers).json()
    everything = client.get(base, headers=headers).json()

    assert [m["content"] for m in last] == ["m4", "m5", "m6"]
    assert [m["content"] for m in before] == ["m1", "m2", "m3"]
    assert len(everything) == len(made)
    segs = client.get(f"/conversations/{data['id']}/segments", headers=headers).json()
    assert segs == []
