"""A reply can ask for a page; the page is written after the reply from the conversation, served
at a secret link with no scripts and an opaque origin, and can be deleted."""

import pytest

from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core.conversation import artifacts
from core.identity.genesis import run_genesis
from core.initiatives import push
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login

PAGE = (
    "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>Santiago</title>"
    "<style>body{font:16px system-ui}</style></head><body><h1>Santiago a dois</h1></body></html>"
)


def world(
    client, db, *, reply="Vou montar o roteiro.\n\n[[página: Santiago a Dois 2027]]", page=PAGE
):
    prompts = []

    def respond(messages):
        if messages[0].content == artifacts.INSTRUCTIONS:
            prompts.append(messages)
            return page
        return reply

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_settings] = lambda: Settings()
    run_genesis(db)
    db.commit()
    return prompts


@pytest.fixture
def pushes(monkeypatch):
    calls = []
    monkeypatch.setattr(push, "send_to_owner", lambda db, owner_id, **kw: calls.append(kw) or 1)
    return calls


def _ask(client, headers, text="monta uma página com o roteiro de Santiago"):
    conversation = client.post("/conversations", headers=headers).json()["id"]
    turn = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": text}
    )
    assert turn.status_code == 200, turn.text
    return conversation, turn.json()


def test_a_reply_that_asks_for_a_page_gets_one_at_a_secret_link(client, db, pushes):
    prompts = world(client, db)
    headers = _login(client, db)
    conversation, turn = _ask(client, headers)

    reply = turn["assistant_message"]
    assert "[[" not in reply["content"] and reply["content"] == "Vou montar o roteiro."
    assert reply["artifact"]["title"] == "Santiago a Dois 2027"
    assert reply["artifact"]["status"] == "pending" and reply["artifact"]["path"] is None

    material = prompts[-1][1].content
    assert "Santiago a Dois 2027" in material and "roteiro de Santiago" in material
    ready = client.get(f"/artifacts/{reply['artifact']['id']}", headers=headers).json()
    assert ready["status"] == "ready" and ready["path"].startswith("/p/")
    # Nobody was looking while it was written: it also goes as a notification.
    assert pushes and "Santiago a Dois 2027" in pushes[0]["body"]

    page = client.get(ready["path"])
    assert page.status_code == 200 and "<h1>Santiago a dois</h1>" in page.text
    policy = page.headers["content-security-policy"]
    assert "default-src 'none'" in policy and "sandbox" in policy
    assert "allow-same-origin" not in policy and "allow-scripts" not in policy
    assert page.headers["referrer-policy"] == "no-referrer"

    history = client.get(f"/conversations/{conversation}/messages", headers=headers).json()
    assert history[-1]["artifact"]["status"] == "ready"


def test_it_knows_it_can_make_pages_and_how(client, db):
    world(client, db, reply="oi")
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    llm = client.app.dependency_overrides[get_llm_provider]()
    client.post(f"/conversations/{conversation}/messages", headers=headers, json={"content": "oi"})
    assert "[[página: Título curto]]" in llm.prompts[-1][0].content


def test_a_reply_that_is_only_the_marker_still_says_something(client, db, pushes):
    world(client, db, reply="[[pagina: Plano]]")
    headers = _login(client, db)
    _, turn = _ask(client, headers)
    assert turn["assistant_message"]["content"].startswith("Vou montar a página “Plano”")


def test_when_the_model_does_not_return_a_page_it_says_so(client, db, pushes):
    world(client, db, page="Desculpe, não consigo.")
    headers = _login(client, db)
    _, turn = _ask(client, headers)
    failed = client.get(
        f"/artifacts/{turn['assistant_message']['artifact']['id']}", headers=headers
    ).json()
    assert failed["status"] == "failed" and failed["path"] is None and failed["error"]
    assert pushes == []


def test_a_page_cut_in_the_middle_is_not_served(client, db, pushes):
    world(client, db, page="<!doctype html><html><body><h1>Meio")
    headers = _login(client, db)
    _, turn = _ask(client, headers)
    failed = client.get(
        f"/artifacts/{turn['assistant_message']['artifact']['id']}", headers=headers
    ).json()
    assert failed["status"] == "failed" and "cortada" in failed["error"]


def test_only_the_owner_sees_the_status_and_a_deleted_link_stops_working(client, db, pushes):
    world(client, db)
    owner = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    _, turn = _ask(client, owner)
    artifact_id = turn["assistant_message"]["artifact"]["id"]
    path = client.get(f"/artifacts/{artifact_id}", headers=owner).json()["path"]

    assert client.get(f"/artifacts/{artifact_id}", headers=other).status_code == 404
    assert client.delete(f"/artifacts/{artifact_id}", headers=other).status_code == 404
    assert [a["id"] for a in client.get("/artifacts", headers=owner).json()] == [artifact_id]
    assert client.get("/artifacts", headers=other).json() == []

    assert client.delete(f"/artifacts/{artifact_id}", headers=owner).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get("/p/nao-existe-nem-de-longe-123").status_code == 404


def test_markers_and_pages_are_read_strictly():
    text, request = artifacts.take_marker("Feito.\n[[ Página :  Viagem ao Chile ]]")
    assert text == "Feito." and request.title == "Viagem ao Chile"
    assert artifacts.take_marker("sem página aqui")[1] is None
    fenced = "```html\n" + PAGE + "\n```"
    assert artifacts.extract_html(fenced) == PAGE
    assert artifacts.extract_html("Aqui está:\n" + PAGE + "\nEspero que goste") == PAGE
    with pytest.raises(artifacts.ArtifactError):
        artifacts.extract_html("<p>só um pedaço</p>")
