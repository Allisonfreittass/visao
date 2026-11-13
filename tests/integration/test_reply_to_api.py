"""Responder on a message: the answer carries the quote, the model knows which message it is about,
and only messages of the same conversation can be answered."""

import uuid

from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core.identity.genesis import run_genesis
from infrastructure.database.models import Message
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login


def world(client, db):
    llm = FakeLLMProvider(reply_text="Pode ser no sábado, então.")
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm


def _send(client, headers, conversation, content, reply_to=None):
    response = client.post(
        f"/conversations/{conversation}/messages",
        headers=headers,
        json={"content": content, "reply_to_id": reply_to},
    )
    return response


def test_answering_a_specific_message_carries_the_quote_to_the_model_and_the_app(client, db):
    llm = world(client, db)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    first = _send(client, headers, conversation, "vamos marcar a revisão do código?").json()
    _send(client, headers, conversation, "outra coisa: e o Pi?")
    answered = first["assistant_message"]["id"]

    turn = _send(client, headers, conversation, "sábado de manhã", reply_to=answered)

    assert turn.status_code == 200, turn.text
    quote = turn.json()["user_message"]["reply_to"]
    assert quote == {"id": answered, "role": "assistant", "excerpt": "Pode ser no sábado, então."}
    last = llm.prompts[-1][-1].content
    assert last.startswith("[Respondendo a esta mensagem sua: «Pode ser no sábado, então.»]")
    assert last.endswith("sábado de manhã")
    history = client.get(f"/conversations/{conversation}/messages", headers=headers).json()
    assert history[-2]["reply_to"]["id"] == answered


def test_an_opening_it_sent_on_its_own_can_be_answered_too(client, db):
    llm = world(client, db)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    _send(client, headers, conversation, "oi")
    opening = Message(
        conversation_id=uuid.UUID(conversation),
        role="assistant",
        content="Sobre o Pi: você pensa em tirar o Nobi da Vercel?",
        origin="initiative",
    )
    db.add(opening)
    db.commit()

    turn = _send(client, headers, conversation, "só um ambiente de teste", reply_to=str(opening.id))

    assert turn.status_code == 200
    assert "«Sobre o Pi: você pensa em tirar o Nobi da Vercel?»" in llm.prompts[-1][-1].content


def test_a_message_from_another_conversation_cannot_be_answered(client, db):
    world(client, db)
    headers = _login(client, db)
    one = client.post("/conversations", headers=headers).json()["id"]
    other = client.post("/conversations", headers=headers).json()["id"]
    elsewhere = _send(client, headers, one, "oi").json()["assistant_message"]["id"]
    assert _send(client, headers, other, "isso", reply_to=elsewhere).status_code == 422
