"""Projetos: a subject with its conversations, pages and files; a conversation in it knows what
was said in the others; deleting a project keeps everything that was in it."""

import io

from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core.identity.genesis import run_genesis
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login


def world(client, db):
    llm = FakeLLMProvider(reply_text="Anotado.")
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm


def _say(client, headers, conversation, text, **extra):
    response = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": text, **extra}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_project_gathers_conversations_files_and_shares_context(client, db):
    llm = world(client, db)
    headers = _login(client, db)
    project = client.post(
        "/projects", headers=headers, json={"name": "  Viagem   Santiago "}
    ).json()
    assert project["name"] == "Viagem Santiago" and project["conversations"] == 0

    first = client.post(f"/conversations?project_id={project['id']}", headers=headers).json()
    assert first["project_id"] == project["id"]
    note = client.post(
        "/attachments",
        headers=headers,
        files={"file": ("roteiro.md", io.BytesIO(b"# dia 1"), "text/markdown")},
    ).json()
    _say(client, headers, first["id"], "o hotel é o Hostal Andino", attachment_ids=[note["id"]])

    loose = client.post("/conversations", headers=headers).json()["id"]
    moved = client.put(
        f"/conversations/{loose}/project", headers=headers, json={"project_id": project["id"]}
    )
    assert moved.json()["project_id"] == project["id"]
    _say(client, headers, loose, "qual era o hotel mesmo?")

    system = llm.prompts[-1][0].content
    assert "Esta conversa faz parte do projeto «Viagem Santiago»" in system
    assert "Pessoa: o hotel é o Hostal Andino" in system and "roteiro.md" in system

    detail = client.get(f"/projects/{project['id']}", headers=headers).json()
    assert detail["conversations"] == 2 and detail["files"] == 1
    assert {c["title"] for c in detail["conversation_list"]} == {
        "o hotel é o Hostal Andino",
        "qual era o hotel mesmo?",
    }
    assert detail["file_list"][0]["filename"] == "roteiro.md"


def test_a_conversation_outside_projects_gets_no_project_context(client, db):
    llm = world(client, db)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    _say(client, headers, conversation, "oi")
    assert "faz parte do projeto" not in llm.prompts[-1][0].content


def test_projects_are_private_and_deleting_one_keeps_its_conversations(client, db):
    world(client, db)
    owner = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    project = client.post("/projects", headers=owner, json={"name": "Pi"}).json()
    conversation = client.post(f"/conversations?project_id={project['id']}", headers=owner).json()[
        "id"
    ]

    assert client.get(f"/projects/{project['id']}", headers=other).status_code == 404
    assert (
        client.post(f"/conversations?project_id={project['id']}", headers=other).status_code == 404
    )
    theirs = client.post("/conversations", headers=other).json()["id"]
    assert (
        client.put(
            f"/conversations/{theirs}/project", headers=other, json={"project_id": project["id"]}
        ).status_code
        == 404
    )
    assert client.get("/projects", headers=other).json() == []

    renamed = client.patch(
        f"/projects/{project['id']}", headers=owner, json={"name": "Raspberry Pi"}
    )
    assert renamed.json()["name"] == "Raspberry Pi"
    assert client.delete(f"/projects/{project['id']}", headers=owner).status_code == 204
    listed = {c["id"]: c for c in client.get("/conversations", headers=owner).json()}
    assert listed[conversation]["project_id"] is None
