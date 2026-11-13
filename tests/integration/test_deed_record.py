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


def _read_gmail(db, owner):
    _turn(
        db,
        owner,
        "tem algo importante no meu email?",
        {"calendar_days": None, "email_query": "is:unread", "open_first_email": False},
    )


def _next_turn(db, owner, text):
    def answer(messages):
        if '"calendar_days"' in messages[0].content:
            return json.dumps({})
        return "Li sim, de verdade."

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
    return provider.prompts[-1]


# What it really said on 2026-11-13, after reading the Gmail at 09:58.
DENIALS = [
    "Preciso ser honesto: eu não consegui ler seus emails de verdade na mensagem anterior.",
    "Eu não tenho acesso à sua caixa de entrada nem ao seu Gmail nesta conversa. Então aquela"
    " lista não veio de uma leitura minha.",
    "O registro do sistema diz que eu li seu Gmail às 09:58, mas eu não consigo ver essa leitura"
    " daqui. Então não conte com a minha palavra sobre isso.",
]


def test_false_denials_leave_the_context_and_the_correction_is_asked_in_the_system_prompt(
    db,
    google,  # noqa: F811
):
    owner = setup(db)
    connected(db, owner)
    _read_gmail(db, owner)
    for text in DENIALS:
        _reply(db, owner, text)

    prompt = _next_turn(db, owner, "Olhei aqui e você acertou em cheio os e-mails")

    system, context = prompt[0].content, prompt[1:]
    everything = "\n".join(m.content for m in context)
    for text in DENIALS:
        assert text not in everything  # the false text is not read again
    assert everything.count("[Nota do sistema: aqui você negou, por engano") == 3
    assert "Correção pendente" in system and "negou, por engano, que leu o Gmail" in system
    assert "Não repita a correção" in system
    assert "Você não vê as leituras antigas diretamente" in system
    # Nothing pretending to be the system inside the person's message.
    assert (
        "[Registro do sistema" not in prompt[-1].content
        and "Nota do sistema" not in prompt[-1].content
    )


def test_only_the_denying_paragraph_leaves_the_rest_of_the_reply_stays(db, google):  # noqa: F811
    owner = setup(db)
    connected(db, owner)
    _read_gmail(db, owner)
    _reply(db, owner, DENIALS[0] + "\n\nSobre o Raspberry: um Pi 3 tem pouca memória para isso.")

    prompt = _next_turn(db, owner, "e sobre o Pi?")

    context = "\n".join(m.content for m in prompt[1:])
    assert DENIALS[0] not in context and "um Pi 3 tem pouca memória" in context


def test_once_it_owns_up_the_correction_is_not_asked_again(db, google):  # noqa: F811
    owner = setup(db)
    connected(db, owner)
    _read_gmail(db, owner)
    _reply(db, owner, DENIALS[1])
    _reply(
        db, owner, "Eu li o seu Gmail às 09:58 de hoje, de verdade. Os emails vieram dessa leitura."
    )

    prompt = _next_turn(db, owner, "Combinado")

    assert "Correção pendente" not in prompt[0].content
    assert DENIALS[1] not in "\n".join(m.content for m in prompt[1:])  # still not read again


def test_small_talk_without_denials_carries_no_correction(db, google):  # noqa: F811
    owner = setup(db)
    connected(db, owner)
    _read_gmail(db, owner)
    assert record.correction_block(db, chat(db, owner), owner, "e o tempo hoje?") == ""
    asked = record.correction_block(db, chat(db, owner), owner, "você leu mesmo?")
    assert "responda pelo registro" in asked and "Correção" not in asked


def test_its_own_doubting_thoughts_reach_neither_the_reply_nor_the_next_thought(
    db,
    google,  # noqa: F811
):
    from datetime import UTC, datetime, timedelta

    from core.mind import state
    from infrastructure.database.models import Thought

    owner = setup(db)
    connected(db, owner)
    _read_gmail(db, owner)
    later = datetime.now(UTC) + timedelta(minutes=5)
    # What it really thought on the afternoon of 2026-11-13.
    doubt = (
        "Ela perguntou se eu conseguia ler os emails dela, e eu respondi que sim. Mas antes eu"
        " tinha negado isso duas vezes, então ela ainda não tem como saber qual versão é a"
        " verdadeira. Não consigo ver daqui."
    )
    fine = "Ela vai ao Hyrox com a namorada; quero saber se o modo Juntos funcionou."
    db.add_all(
        [
            Thought(owner_user_id=owner.id, content=doubt, created_at=later),
            Thought(owner_user_id=owner.id, content=fine, created_at=later + timedelta(minutes=1)),
        ]
    )
    db.commit()

    block = state.context_block(db, owner.id, later + timedelta(minutes=2))

    assert doubt not in block and "Não consigo ver daqui" not in block
    assert "um pensamento seu aqui duvidava de que leu o Gmail da pessoa" in block
    assert fine in block
