"""A message runs one turn, and a turn that did something says so even when the model fails
(docs/research/comparativo_agentes.md, F2 and F3)."""

import json
import threading
import uuid

import pytest

from apps.api.llm import get_llm_provider
from core import actions
from core.conversation import turn_lock
from core.conversation.service import REPLY_BY_CODE_OPENING
from core.decision.pipeline import _done_before_the_reply
from infrastructure.database.models import Decision, Message, Project
from integrations.llm.base import LLMError
from tests.fakes import FakeLLMProvider
from tests.integration.test_app_actions_api import (
    ASKED,
    CHILE,
    NOTES,
    _continuous,
    _login,
    _said_before,
    world,
)

DEEDS = [
    {"do": "create_project", "name": CHILE},
    {"do": "add_notes", "project": CHILE, "lines": NOTES},
]


def _post(client, headers, conversation, text, client_id=None):
    body = {"content": text}
    if client_id is not None:
        body["client_message_id"] = str(client_id)
    return client.post(f"/conversations/{conversation}/messages", headers=headers, json=body)


def _app_actions(db):
    return [a for d in db.query(Decision).all() for a in d.actions if a["action"] == "app_actions"]


# F2 ------------------------------------------------------------------------------------------


def test_the_same_message_sent_twice_runs_one_turn(client, db):
    # A retry on a bad network: the second copy gets the first turn back; nothing is done twice.
    llm = world(client, db, actions_answer=[DEEDS, DEEDS], reply="Anotei no projeto.")
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    _said_before(db, conversation)
    sent = uuid.uuid4()

    first = _post(client, headers, conversation, ASKED, sent)
    calls = len(llm.prompts)
    again = _post(client, headers, conversation, ASKED, sent)

    assert first.status_code == again.status_code == 200
    assert again.json()["assistant_message"]["id"] == first.json()["assistant_message"]["id"]
    assert again.json()["user_message"]["id"] == first.json()["user_message"]["id"]
    assert len(llm.prompts) == calls  # no model call for the copy
    project = db.query(Project).one()
    assert project.notes.splitlines() == [f"- {line}" for line in NOTES]  # written once
    assert len(_app_actions(db)) == 1
    assert db.query(Message).filter(Message.content == ASKED).count() == 1


def test_a_copy_of_a_message_whose_turn_failed_runs_again(client, db):
    llm = world(client, db, reply="Oi.")
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    sent = uuid.uuid4()
    llm.fail_with = "http_500"
    assert _post(client, headers, conversation, "oi", sent).status_code == 502
    llm.fail_with = None
    retried = _post(client, headers, conversation, "oi", sent)
    assert retried.status_code == 200 and retried.json()["assistant_message"]["content"] == "Oi."


def test_a_message_while_the_conversation_is_still_answering_is_turned_away(
    client, db, monkeypatch
):
    world(client, db, reply="Oi.")
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    entered, leave = threading.Event(), threading.Event()

    def answering():
        with turn_lock.held(db, uuid.UUID(conversation)):
            entered.set()
            leave.wait(5)

    other = threading.Thread(target=answering)
    other.start()
    entered.wait(5)
    monkeypatch.setattr(turn_lock, "WAIT_SECONDS", 0.05)
    try:
        busy = _post(client, headers, conversation, "oi")
    finally:
        leave.set()
        other.join(5)
    assert busy.status_code == 409 and "Ainda respondendo" in busy.json()["detail"]
    assert _post(client, headers, conversation, "oi").status_code == 200


# F3 ------------------------------------------------------------------------------------------


def _reply_fails(client, failure):
    """The actions are planned; the reply itself fails (`failure`: an LLMError kind, or "")."""

    def respond(messages):
        if messages[0].content == actions.INSTRUCTIONS:
            return json.dumps({"actions": DEEDS})
        if failure:
            raise LLMError(failure, "falha simulada")
        return "   "  # an empty reply

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm


@pytest.mark.parametrize("failure", ["http_500", ""])
def test_when_the_model_fails_after_doing_things_code_says_what_was_done(client, db, failure):
    world(client, db)
    _reply_fails(client, failure)
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    _said_before(db, conversation)
    sent = uuid.uuid4()

    turn = _post(client, headers, conversation, ASKED, sent)

    assert turn.status_code == 200, turn.text
    reply = turn.json()["assistant_message"]
    assert reply["origin"] == "fallback"
    assert reply["content"].startswith(REPLY_BY_CODE_OPENING)
    assert f"- Criei o projeto «{CHILE}»" in reply["content"]
    assert db.query(Project).one().name == CHILE
    done = [a for d in db.query(Decision).all() for a in d.actions]
    assert any(a["action"] == "reply_by_code" for a in done)
    assert db.query(Message).filter(Message.content == ASKED).count() == 1
    # Sent again, it gets the same answer back and does nothing again.
    again = _post(client, headers, conversation, ASKED, sent)
    assert again.json()["assistant_message"]["id"] == reply["id"]
    assert db.query(Project).one().notes.splitlines() == [f"- {line}" for line in NOTES]


def test_when_the_model_fails_and_nothing_was_done_the_error_stays(client, db):
    llm = world(client, db)
    llm.fail_with = "http_500"
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    assert _post(client, headers, conversation, "oi").status_code == 502
    assert db.query(Message).filter(Message.role == "assistant").count() == 0


def test_what_waits_for_a_yes_or_a_tap_is_said_as_waiting():
    waiting = actions.Deed(
        "delete_project", "apagar o projeto «Chile»: espera o sim dela", False, True
    )
    failed = actions.Deed("create_project", "não criei: projetos demais", False)
    facts = _done_before_the_reply(
        [waiting, failed], None, None, ["deixei o pedido ao Mac esperando o seu Aprovar (visao)"]
    )
    assert facts == [
        "apagar o projeto «Chile»: espera o seu sim",
        "não criei: projetos demais",
        "deixei o pedido ao Mac esperando o seu Aprovar (visao)",
    ]
