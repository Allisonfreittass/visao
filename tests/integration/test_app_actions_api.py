"""It does what it says in the app (docs/ACOES.md, ADR-0021): projects, notes and panels changed
from the conversation, deleting only after a yes, and never claiming what was not done.

The real case, 17/11/2026: "Vamos fechar com o JetSMART. Apenas deixar anotado isso tudo em um
único projeto, que é Viagem para o Chile" got "Anotado: ..." with no project and no note."""

import json
import uuid
from datetime import UTC, datetime, timedelta

from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core import actions
from core.identity.capabilities import Capabilities
from core.identity.genesis import run_genesis
from infrastructure.database.models import (
    Conversation,
    Decision,
    Message,
    Panel,
    PendingAction,
    Project,
    User,
)
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login

ASKED = (
    "Vamos fechar com o JetSMART. Apenas deixar anotado isso tudo em um único projeto, que é "
    "Viagem para o Chile"
)
CHILE = "Viagem para o Chile"
NOTES = [
    "Voo JetSMART de Guarulhos (GRU) para Santiago, de 3 a 13/08/2027",
    "R$ 2.047 para 2 pessoas",
    "Falta comprar no site da JetSMART",
]


def world(client, db, *, actions_answer=None, reply="Feito."):
    answers = list(actions_answer or [])

    def respond(messages):
        if messages[0].content == actions.INSTRUCTIONS:
            return json.dumps({"actions": answers.pop(0) if answers else []})
        return reply

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm


def _continuous(client, headers):
    return client.get("/conversations/continuous", headers=headers).json()["id"]


def _said_before(db, conversation_id):
    conversation = db.get(Conversation, uuid.UUID(conversation_id))
    start = datetime.now(UTC) - timedelta(minutes=10)
    for n, (role, text) in enumerate(
        [
            ("user", "quero ir a Santiago em agosto, saindo de Guarulhos"),
            (
                "assistant",
                "Opção mais barata: JetSMART GRU → SCL, 3 a 13/08/2027, R$ 2.047 para 2 pessoas.",
            ),
        ]
    ):
        db.add(
            Message(
                conversation_id=conversation.id,
                role=role,
                content=text,
                created_at=start + timedelta(minutes=n),
            )
        )
    db.commit()


def _send(client, headers, conversation, text):
    response = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": text}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _actions_done(db):
    return [a for d in db.query(Decision).all() for a in d.actions if a["action"] == "app_actions"]


def _chat_prompt(llm):
    return next(p for p in reversed(llm.prompts) if p[0].content != actions.INSTRUCTIONS)


def test_the_real_case_creates_the_project_and_writes_the_notes(client, db):
    llm = world(
        client,
        db,
        actions_answer=[
            [
                {"do": "create_project", "name": CHILE},
                {"do": "add_notes", "project": CHILE, "lines": NOTES},
            ]
        ],
        reply="Anotei no projeto Viagem para o Chile: o voo da JetSMART e o que falta.",
    )
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    _said_before(db, conversation)

    turn = _send(client, headers, conversation, ASKED)

    project = db.query(Project).one()
    assert project.name == CHILE
    assert project.notes.splitlines() == [f"- {line}" for line in NOTES]
    system = _chat_prompt(llm)[0].content
    assert "criei o projeto «Viagem para o Chile»" in system
    assert "anotei 3 linha(s)" in system
    # The claim is true this time, so it stays.
    assert "Anotei no projeto" in turn["assistant_message"]["content"]
    assert _actions_done(db)[0]["executed"] is True
    detail = client.get(f"/projects/{project.id}", headers=headers).json()
    assert detail["notes"].startswith("- Voo JetSMART")


def test_a_note_with_a_number_not_said_is_not_written(client, db):
    world(
        client,
        db,
        actions_answer=[
            [
                {"do": "create_project", "name": CHILE},
                {"do": "add_notes", "project": CHILE, "lines": ["Hotel por R$ 9.999"]},
            ]
        ],
    )
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    _said_before(db, conversation)
    _send(client, headers, conversation, ASKED)
    assert db.query(Project).one().notes == ""
    assert any("não anotei 1 linha" in d for d in _actions_done(db)[0]["deeds"])


def test_deleting_waits_for_a_yes(client, db):
    llm = world(client, db, actions_answer=[[{"do": "delete_project", "project": "chile"}]])
    headers = _login(client, db)
    owner = db.query(User).one()
    project = Project(owner_user_id=owner.id, name=CHILE, notes="- algo")
    db.add(project)
    db.commit()
    conversation = _continuous(client, headers)

    _send(client, headers, conversation, "apaga o projeto do chile")
    assert db.query(Project).count() == 1
    assert "espera o sim dela" in _chat_prompt(llm)[0].content
    assert db.query(PendingAction).one().status == "pending"

    _send(client, headers, conversation, "sim, apaga")
    assert db.query(Project).count() == 0
    assert "apaguei o projeto «Viagem para o Chile»" in _chat_prompt(llm)[0].content


def test_a_no_keeps_it(client, db):
    world(client, db, actions_answer=[[{"do": "delete_project", "project": CHILE}]])
    headers = _login(client, db)
    owner = db.query(User).one()
    db.add(Project(owner_user_id=owner.id, name=CHILE))
    db.commit()
    conversation = _continuous(client, headers)
    _send(client, headers, conversation, "apaga o projeto Viagem para o Chile")
    _send(client, headers, conversation, "não, deixa")
    assert db.query(Project).count() == 1
    assert db.query(PendingAction).one().status == "dropped"


def test_a_panel_is_paused_and_put_in_a_project(client, db):
    world(
        client,
        db,
        actions_answer=[
            [
                {"do": "move", "what": "panel", "item": "santiago", "project": CHILE},
                {"do": "pause_panel", "panel": "Viagem Santiago de Guarulhos"},
            ]
        ],
    )
    headers = _login(client, db)
    owner = db.query(User).one()
    project = Project(owner_user_id=owner.id, name=CHILE)
    db.add(project)
    db.flush()
    db.add(
        Panel(
            owner_user_id=owner.id,
            title="Viagem Santiago de Guarulhos",
            spec={"destination": "Santiago"},
            status="active",
        )
    )
    db.commit()
    conversation = _continuous(client, headers)
    _send(client, headers, conversation, "põe o painel no projeto do Chile e pausa ele")
    panel = db.query(Panel).one()
    assert panel.project_id == project.id and panel.status == "paused"
    assert client.get(f"/projects/{project.id}", headers=headers).json()["panel_list"][0][
        "title"
    ] == ("Viagem Santiago de Guarulhos")


def test_saying_it_noted_without_noting_loses_that_sentence(client, db):
    world(
        client,
        db,
        reply=(
            "Anotado: a viagem ao Chile fica no projeto Viagem para o Chile. "
            "O JetSMART você fecha no site."
        ),
    )
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    turn = _send(client, headers, conversation, "o que você acha do JetSMART?")
    content = turn["assistant_message"]["content"]
    assert "Anotado" not in content and content == "O JetSMART você fecha no site."
    assert any(a["action"] == "claim_removed" for d in db.query(Decision).all() for a in d.actions)


def test_the_notes_come_back_when_the_subject_does(client, db):
    llm = world(client, db)
    headers = _login(client, db)
    owner = db.query(User).one()
    db.add(Project(owner_user_id=owner.id, name=CHILE, notes="\n".join(f"- {n}" for n in NOTES)))
    db.commit()
    conversation = _continuous(client, headers)
    _send(client, headers, conversation, "e o voo da JetSMART pra Santiago, quanto ficou mesmo?")
    system = _chat_prompt(llm)[0].content
    assert "Anotações do projeto «Viagem para o Chile»" in system and "R$ 2.047" in system
    _send(client, headers, conversation, "bom dia!")
    assert "Anotações do projeto" not in _chat_prompt(llm)[0].content


def test_the_manifest_and_the_unrelated_messages():
    said = "; ".join(Capabilities(browser=True).actions())
    assert "projetos pela conversa" in said
    assert not actions.candidate("bom dia, tudo bem?")
    assert actions.candidate(ASKED)


def test_a_yes_to_its_own_offer_does_it(client, db):
    """17/11/2026: "Quer que eu acrescente essas informações agora?" / "Por favor" got "Não
    consigo acrescentar isso agora"."""
    llm = world(
        client,
        db,
        actions_answer=[[{"do": "add_notes", "project": CHILE, "lines": ["Hotel em Providencia"]}]],
        reply="Acrescentei o hotel nas anotações.",
    )
    headers = _login(client, db)
    owner = db.query(User).one()
    db.add(Project(owner_user_id=owner.id, name=CHILE))
    db.commit()
    conversation = _continuous(client, headers)
    db.add(
        Message(
            conversation_id=uuid.UUID(conversation),
            role="assistant",
            content="Quer que eu acrescente essas informações agora?",
        )
    )
    db.commit()

    _send(client, headers, conversation, "Por favor")

    assert db.query(Project).one().notes == "- Hotel em Providencia"
    assert "anotei 1 linha(s)" in _chat_prompt(llm)[0].content


def test_saying_it_cannot_add_when_it_can_loses_that_sentence(client, db):
    world(client, db, reply="Não consigo acrescentar isso agora. Me passa o texto que eu ajeito.")
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    turn = _send(client, headers, conversation, "o que falta decidir da viagem?")
    assert turn["assistant_message"]["content"] == "Me passa o texto que eu ajeito."


def test_a_project_has_its_own_chat_and_its_own_panels(client, db):
    world(client, db)
    headers = _login(client, db)
    owner = db.query(User).one()
    project = Project(owner_user_id=owner.id, name=CHILE)
    db.add(project)
    db.flush()
    db.add(
        Panel(
            owner_user_id=owner.id,
            project_id=project.id,
            title="Santiago",
            spec={"destination": "Santiago"},
            status="active",
        )
    )
    db.commit()

    first = client.get(f"/conversations/project/{project.id}", headers=headers).json()
    again = client.get(f"/conversations/project/{project.id}", headers=headers).json()

    assert first["id"] == again["id"] and first["project_id"] == str(project.id)
    assert first["continuous"] is False
    listed = client.get("/panels", headers=headers).json()
    assert listed[0]["project_id"] == str(project.id)


def test_send_it_to_the_project_does_it_instead_of_handing_it_over(client, db):
    """17/11/2026: "Envie o preço do voo pro projeto" got "Você pode colar este texto na tela do
    projeto"."""
    llm = world(
        client,
        db,
        actions_answer=[
            [{"do": "add_notes", "project": CHILE, "lines": ["R$ 2.047 para 2 pessoas"]}]
        ],
        reply='Você pode colar este texto na tela do projeto "Viagem para o Chile":\n\nR$ 2.047',
    )
    headers = _login(client, db)
    owner = db.query(User).one()
    db.add(Project(owner_user_id=owner.id, name=CHILE))
    db.commit()
    conversation = _continuous(client, headers)
    _said_before(db, conversation)

    _send(client, headers, conversation, "Envie o preço do voo pro projeto")

    assert db.query(Project).one().notes == "- R$ 2.047 para 2 pessoas"
    assert "anotei 1 linha(s)" in _chat_prompt(llm)[0].content


def test_handing_it_over_is_removed_when_nothing_was_done(client, db):
    world(client, db, reply="Você pode colar este texto no projeto. Boa viagem para vocês!")
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    turn = _send(client, headers, conversation, "como está a viagem?")
    assert turn["assistant_message"]["content"] == "Boa viagem para vocês!"


def test_the_project_chat_opens_with_what_was_noted_and_the_reply_points_to_it(client, db):
    world(
        client,
        db,
        actions_answer=[
            [
                {"do": "create_project", "name": CHILE},
                {"do": "add_notes", "project": CHILE, "lines": NOTES},
            ],
            [{"do": "add_notes", "project": CHILE, "lines": ["Hotel em Providencia"]}],
        ],
        reply="Anotei no projeto.",
    )
    headers = _login(client, db)
    conversation = _continuous(client, headers)
    _said_before(db, conversation)

    turn = _send(client, headers, conversation, ASKED)

    project = db.query(Project).one()
    assert turn["assistant_message"]["project_id"] == str(project.id)
    chat = client.get(f"/conversations/project/{project.id}", headers=headers).json()
    said = client.get(f"/conversations/{chat['id']}/messages", headers=headers).json()
    assert len(said) == 1 and said[0]["origin"] == "project"
    assert said[0]["content"].startswith("Aqui fica tudo de «Viagem para o Chile»")
    # The notes are in the card on top; the opening points there instead of repeating them.
    assert "no cartão aqui em cima" in said[0]["content"]
    assert "R$ 2.047" not in said[0]["content"]

    # More notes from the main conversation are said in the project's chat too.
    _send(client, headers, conversation, "anota no projeto que o hotel é em Providencia")
    said = client.get(f"/conversations/{chat['id']}/messages", headers=headers).json()
    assert said[-1]["content"] == "Anotei:\n- Hotel em Providencia"


def test_a_project_made_by_the_button_opens_its_chat_with_a_hello(client, db):
    world(client, db)
    headers = _login(client, db)
    project = client.post("/projects", headers=headers, json={"name": "Casa nova"}).json()
    chat = client.get(f"/conversations/project/{project['id']}", headers=headers).json()
    said = client.get(f"/conversations/{chat['id']}/messages", headers=headers).json()
    assert said[0]["content"].startswith("Aqui fica tudo de «Casa nova». Pode me pedir")
