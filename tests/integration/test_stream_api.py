"""The turn as server-sent events (docs/decisions/0011): steps, the text as it is written, the
kept text at the end (a `replace` when the rule check changed it), and a `done` with the same
reply the POST returns. Parar, a timeout and a client that left never leave a half message."""

import json
import uuid

import pytest

from apps.api.llm import get_llm_provider
from apps.api.routes import conversations as routes
from apps.api.settings import Settings, get_settings
from core.conversation import progress
from core.identity.genesis import run_genesis
from infrastructure.database.models import Message, ModelUsage
from integrations.llm.base import LLMError, should_stop, tell_draft
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    progress.reset()
    monkeypatch.setattr(routes, "STREAM_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(routes, "STREAM_TICK_SECONDS", 0.01)
    yield
    progress.reset()


def world(client, db, pieces, *, fail_after=None, stop_after=None):
    """A provider that streams `pieces`; it can fail with a kind, or Parar, after some of them."""

    def respond(messages):
        written = ""
        conversation_id = progress._current.get()
        for n, piece in enumerate(pieces):
            if stop_after is not None and n == stop_after:
                progress.cancel(conversation_id)
            if should_stop():
                raise LLMError("cancelled", "parado")
            if fail_after is not None and n == fail_after:
                raise LLMError("timeout", "demorou")
            written += piece
            tell_draft(written)
        return written

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_settings] = lambda: Settings()
    run_genesis(db)
    db.commit()
    return llm


def read(client, headers, conversation, last=None):
    """The events the stream sends, as (id, kind, data)."""
    extra = {"Last-Event-ID": str(last)} if last is not None else {}
    events, current = [], {}
    with client.stream(
        "GET", f"/conversations/{conversation}/stream", headers={**headers, **extra}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        for line in response.iter_lines():
            if line.startswith("id: "):
                current["id"] = int(line[4:])
            elif line.startswith("event: "):
                current["kind"] = line[7:]
            elif line.startswith("data: "):
                current["data"] = json.loads(line[6:])
            elif line == "" and "kind" in current:
                events.append((current["id"], current["kind"], current["data"]))
                current = {}
    return events


def send(client, headers, text, conversation=None):
    conversation = conversation or client.post("/conversations", headers=headers).json()["id"]
    turn = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": text}
    )
    return conversation, turn


def text_of(events):
    shown = ""
    for _, kind, data in events:
        if kind == "delta":
            shown += data["text"]
        elif kind == "replace":
            shown = data["text"]
    return shown


def test_the_text_chat_streams_steps_text_and_a_done_with_the_reply(client, db):
    world(client, db, ["Camberra ", "é a capital. ", "[[+]]\n", "Fica no sudeste."])
    headers = _login(client, db)
    conversation, turn = send(client, headers, "Qual é a capital da Austrália?")
    assert turn.status_code == 200

    events = read(client, headers, conversation, last=0)

    kinds = [kind for _, kind, _ in events]
    assert kinds[0] == "step" and kinds[-1] == "done" and "delta" in kinds
    assert [d["label"] for _, k, d in events if k == "step"][:2] == [
        "Pensando",
        "Escrevendo a resposta",
    ]
    assert all("kind" in d for _, k, d in events if k == "step")
    reply = turn.json()["assistant_message"]
    assert text_of(events) == reply["content"] == "Camberra é a capital.\n\nFica no sudeste."
    assert "[[" not in "".join(d.get("text", "") for _, _, d in events)
    done = events[-1][2]
    assert done["assistant_message"]["id"] == reply["id"]
    assert done["assistant_message"]["parts"] == ["Camberra é a capital.", "Fica no sudeste."]
    ids = [i for i, _, _ in events]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


def test_it_resumes_after_the_last_event_seen(client, db):
    world(client, db, ["Um. ", "Dois. ", "Três."])
    headers = _login(client, db)
    conversation, _ = send(client, headers, "conta até três")
    everything = read(client, headers, conversation, last=0)
    middle = everything[len(everything) // 2][0]

    rest = read(client, headers, conversation, last=middle)

    assert rest == [e for e in everything if e[0] > middle]


def test_the_kept_text_replaces_what_was_shown_when_the_check_changed_it():
    conversation = uuid.uuid4()
    with progress.tracking(conversation):
        progress.draft("Fica em Camberra. Quer saber mais?")
        progress.final("Fica em Camberra.")
    events, state = progress.follow(conversation, 0, 0.0)
    assert [(e.kind, e.data) for e in events] == [
        ("delta", {"text": "Fica em Camberra. Quer saber mais?"}),
        ("replace", {"text": "Fica em Camberra.", "final": True}),
    ]
    # No `done` from the route yet: still live (it closes after UNCLOSED_GRACE_SECONDS at most).
    assert state == "live"


def test_a_marker_being_written_is_held_back_until_it_is_known():
    conversation = uuid.uuid4()
    with progress.tracking(conversation):
        progress.draft("Pronto. [")
        progress.draft("Pronto. [[pá")
        progress.draft("Pronto. [[página: Roteiro]]")
        progress.final("Pronto.")
    events, _ = progress.follow(conversation, 0, 0.0)
    assert [(e.kind, e.data["text"]) for e in events] == [("delta", "Pronto.")]


def test_parar_mid_stream_keeps_no_reply_and_the_stream_says_so(client, db):
    world(client, db, ["Cam", "berra ", "é a capital."], stop_after=1)
    headers = _login(client, db)
    conversation, turn = send(client, headers, "capital?")

    assert turn.status_code == 409
    events = read(client, headers, conversation, last=0)
    assert events[-1][1] == "error" and events[-1][2]["status"] == 409
    assert text_of(events) == "Cam"
    assert db.query(Message).filter_by(role="assistant").count() == 0
    usage = db.query(ModelUsage).filter_by(purpose="chat_reply").one()
    assert (usage.outcome, usage.error_kind) == ("error", "cancelled")


def test_a_timeout_mid_stream_leaves_no_half_message(client, db):
    world(client, db, ["Cam", "berra ", "é a capital."], fail_after=2)
    headers = _login(client, db)
    conversation, turn = send(client, headers, "capital?")

    assert turn.status_code == 502
    events = read(client, headers, conversation, last=0)
    assert text_of(events) == "Camberra"
    assert events[-1][1] == "error" and events[-1][2]["status"] == 502
    assert db.query(Message).filter_by(role="assistant").count() == 0


def test_a_client_that_leaves_the_stream_does_not_cost_the_reply(client, db):
    world(client, db, ["Um. ", "Dois."])
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    with client.stream("GET", f"/conversations/{conversation}/stream", headers=headers) as r:
        assert r.status_code == 200  # opened and dropped before the turn
    _, turn = send(client, headers, "conta", conversation)
    assert turn.status_code == 200
    assert db.query(Message).filter_by(role="assistant").one().content == "Um. Dois."
    assert db.query(ModelUsage).filter_by(purpose="chat_reply").one().outcome == "success"


def test_with_no_turn_it_waits_a_little_and_ends(client, db):
    world(client, db, ["x"])
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    assert read(client, headers, conversation) == []


def test_an_earlier_turn_is_not_replayed_to_a_new_stream(client, db):
    world(client, db, ["Oi."])
    headers = _login(client, db)
    conversation, _ = send(client, headers, "oi")
    assert read(client, headers, conversation) == []


def test_someone_elses_stream_is_not_found(client, db):
    world(client, db, ["x"])
    headers = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    conversation = client.post("/conversations", headers=headers).json()["id"]
    assert client.get(f"/conversations/{conversation}/stream", headers=other).status_code == 404
