"""What it really did stays on record for the next turns and for its thinking, so it never
denies an action that ran (real case, 2026-11-13: it read the Gmail, then apologized for having
"made up" the list two messages later)."""

import json
from dataclasses import replace

from core.decision import record
from core.decision.pipeline import run_turn
from core.identity.genesis import get_identity
from core.mind.think import _owner_recent
from infrastructure.database.models import Artifact, Message
from tests.fakes import FakeLLMProvider
from tests.integration.test_google import KEY, connected, google  # noqa: F401 - fixture
from tests.integration.test_mind import setup
from tests.integration.test_mind_temperament import chat
from tests.integration.test_phase9 import CONFIG


def _turn(db, owner, text, extraction):
    def answer(messages):
        if '"calendar_days"' in messages[0].content:
            return json.dumps(extraction, ensure_ascii=False)
        return "Dei uma olhada nos seus emails não lidos."

    provider = FakeLLMProvider(responder=answer)
    run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text=text,
        provider=provider,
        search=None,
        config=replace(CONFIG, curiosity_enabled=False, google_secret=KEY),
    )
    return provider.prompts[-1][0].content


def test_a_gmail_read_is_on_record_when_asked_about_it_later(db, google):  # noqa: F811
    owner = setup(db)
    connected(db, owner)
    first = _turn(
        db,
        owner,
        "tem algo importante no meu email?",
        {
            "calendar_days": None,
            "email_query": "is:unread newer_than:2d",
            "open_first_email": False,
        },
    )
    assert record.HEADING not in first  # nothing done before the first read

    later = _turn(
        db, owner, "você leu mesmo os meus emails? qual a chance de ser coincidência?", {}
    )

    assert record.HEADING in later
    assert "leu o Gmail da pessoa (busca “is:unread newer_than:2d”, 1 email(s))" in later
    assert "nunca diga que não fez nem peça desculpas por ter feito" in later
    assert "Se antes você negou algo que está aqui, corrija agora" in later


def test_its_thinking_sees_what_it_did_next_to_what_it_said(db, google):  # noqa: F811
    owner = setup(db)
    connected(db, owner)
    _turn(
        db,
        owner,
        "tem algo importante no meu email?",
        {"calendar_days": 2, "email_query": "is:unread", "open_first_email": False},
    )
    mine = [item for item in _owner_recent(db, owner) if item["who"] == "você"]
    assert mine[-1]["did"] == [
        "leu o Gmail da pessoa (busca “is:unread”, 1 email(s))"
        " e leu a Google Agenda (próximos 2 dia(s))"
    ]


def test_only_executed_actions_count_and_pages_are_on_record(db):
    owner = setup(db)
    conversation = chat(db, owner)
    reply = Message(conversation_id=conversation.id, role="assistant", content="Vou montar.")
    db.add(reply)
    db.flush()
    db.add(
        Artifact(
            owner_user_id=owner.id,
            conversation_id=conversation.id,
            message_id=reply.id,
            title="Santiago",
            token="x" * 32,
            status="ready",
        )
    )
    db.flush()

    block = record.conversation_block(db, conversation, owner)

    assert "montou a página “Santiago” (pronta)" in block
    assert record.deeds(
        [
            {"action": "research", "executed": False, "question": "x"},
            {"action": "something_new", "executed": True},
            {"action": "read_links", "executed": True, "opened": ["https://github.com/a/b"]},
        ]
    ) == ["abriu e leu github.com"]


def test_a_conversation_with_only_talk_has_no_record(db):
    owner = setup(db)
    assert record.conversation_block(db, chat(db, owner), owner) == ""


def _reply(db, owner, text):
    conversation = chat(db, owner)
    message = Message(conversation_id=conversation.id, role="assistant", content=text)
    db.add(message)
    db.commit()
    return message


def test_a_later_denial_of_a_real_read_is_corrected_with_the_next_message(db, google):  # noqa: F811
    owner = setup(db)
    connected(db, owner)
    _turn(
        db,
        owner,
        "tem algo importante no meu email?",
        {"calendar_days": None, "email_query": "is:unread", "open_first_email": False},
    )
    # What it really said afterwards (2026-11-13, 12:49 and 12:51).
    _reply(
        db,
        owner,
        "Preciso ser honesto: eu não consegui ler seus emails de verdade na mensagem anterior.",
    )
    _reply(
        db,
        owner,
        "O que sei é o seguinte: eu não tenho acesso à sua caixa de entrada nem ao seu Gmail nesta"
        " conversa. Então aquela lista não veio de uma leitura minha.",
    )

    def answer(messages):
        if '"calendar_days"' in messages[0].content:
            return json.dumps({})
        return "Li sim."

    provider = FakeLLMProvider(responder=answer)
    run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="Olhei aqui e você acertou em cheio os e-mails, qual a chance de ser coincidência?",
        provider=provider,
        search=None,
        config=replace(CONFIG, curiosity_enabled=False, google_secret=KEY),
    )
    last = provider.prompts[-1][-1].content
    assert last.startswith("Olhei aqui e você acertou em cheio")
    assert "[Registro do sistema, não escrito pela pessoa]" in last
    assert "leu o Gmail da pessoa (busca “is:unread”, 1 email(s))" in last
    assert last.count("você disse que não tinha feito isso") == 2
    assert "Corrija agora" in last and "Não volte a negar" in last


def test_small_talk_without_denials_carries_no_correction(db, google):  # noqa: F811
    owner = setup(db)
    connected(db, owner)
    _turn(
        db,
        owner,
        "tem algo importante no meu email?",
        {"calendar_days": None, "email_query": "is:unread", "open_first_email": False},
    )
    assert record.correction_block(db, chat(db, owner), owner, "e o tempo hoje?") == ""
    asked = record.correction_block(db, chat(db, owner), owner, "você leu mesmo?")
    assert "leu o Gmail" in asked and "Corrija" not in asked
