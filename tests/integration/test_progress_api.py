"""The live status says only steps that really run, and a reply also goes as a notification
when the app stopped watching the turn (phone locked), never when nobody was watching at all."""

import io

import pytest

from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core.conversation import progress
from core.identity.genesis import run_genesis
from core.initiatives import push
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login


@pytest.fixture(autouse=True)
def _clean_progress():
    progress.reset()
    yield
    progress.reset()


def world(client, db, during=None):
    seen: list[list[str]] = []

    def respond(messages):
        conversation_id = progress._current.get()
        live = progress.snapshot(conversation_id) if conversation_id else None
        seen.append([s["label"] for s in live["steps"]] if live else [])
        if during:
            during(conversation_id)
        return "Pronto."

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_settings] = lambda: Settings()
    run_genesis(db)
    db.commit()
    return seen


def test_the_steps_that_ran_are_shown_while_it_works(client, db):
    seen = world(client, db)
    headers = _login(client, db)
    file = client.post(
        "/attachments",
        headers=headers,
        files={"file": ("notas.md", io.BytesIO(b"# oi"), "text/markdown")},
    ).json()
    conversation = client.post("/conversations", headers=headers).json()["id"]

    turn = client.post(
        f"/conversations/{conversation}/messages",
        headers=headers,
        json={"content": "resume", "attachment_ids": [file["id"]]},
    )

    assert turn.status_code == 200, turn.text
    steps = seen[-1]
    assert steps[0] == "Pensando" and "Lendo notas.md" in steps
    assert steps[-1] == "Escrevendo a resposta"
    after = client.get(f"/conversations/{conversation}/progress", headers=headers).json()
    assert after["active"] is False and after["steps"][-1]["label"] == "Escrevendo a resposta"


def test_with_nothing_running_there_is_nothing_to_show(client, db):
    world(client, db)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    live = client.get(f"/conversations/{conversation}/progress", headers=headers).json()
    assert live == {"active": False, "elapsed_ms": 0, "steps": []}


def test_someone_elses_progress_is_not_found(client, db):
    world(client, db)
    owner = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    conversation = client.post("/conversations", headers=owner).json()["id"]
    assert client.get(f"/conversations/{conversation}/progress", headers=other).status_code == 404


def _sent(monkeypatch):
    calls = []
    monkeypatch.setattr(push, "send_to_owner", lambda db, owner_id, **kw: calls.append(kw) or 1)
    return calls


def test_a_reply_also_goes_as_a_notification_when_the_app_stopped_watching(client, db, monkeypatch):
    def leave(conversation_id):
        progress._turns[conversation_id].last_seen -= progress.WATCH_GRACE_SECONDS + 1

    world(client, db, during=leave)
    calls = _sent(monkeypatch)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    client.get(
        f"/conversations/{conversation}/progress", headers=headers
    )  # the app starts watching

    client.post(f"/conversations/{conversation}/messages", headers=headers, json={"content": "oi"})

    assert len(calls) == 1
    assert calls[0]["body"] == "Pronto." and calls[0]["url"] == f"/?c={conversation}"


def test_no_notification_while_watching_or_when_nobody_ever_watched(client, db, monkeypatch):
    world(client, db)
    calls = _sent(monkeypatch)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    client.post(f"/conversations/{conversation}/messages", headers=headers, json={"content": "oi"})
    client.get(f"/conversations/{conversation}/progress", headers=headers)
    client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": "e aí"}
    )
    assert calls == []


def test_steps_outside_a_turn_are_ignored():
    progress.step("Pesquisando")  # no tracked turn on this thread
    assert progress._turns == {}


def test_parar_while_it_writes_keeps_no_reply(client, db):
    from infrastructure.database.models import Message

    world(client, db, during=lambda conversation_id: progress.cancel(conversation_id))
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]

    turn = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": "oi"}
    )

    assert turn.status_code == 409 and turn.json()["detail"] == "Parado por você"
    roles = [m.role for m in db.query(Message).all()]
    assert "assistant" not in roles


def test_parar_with_nothing_running_says_so(client, db):
    world(client, db)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    stopped = client.post(f"/conversations/{conversation}/cancel", headers=headers)
    assert stopped.status_code == 200 and stopped.json() == {"cancelled": False}


def test_a_step_after_parar_stops_the_turn():
    import uuid as _uuid

    conversation_id = _uuid.uuid4()
    with progress.tracking(conversation_id):
        progress.step("Pensando")
        assert progress.cancel(conversation_id) is True
        with pytest.raises(progress.TurnCancelled):
            progress.step("Navegando por google.com")
