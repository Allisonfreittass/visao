"""The local model on the owner's Mac (docs/MODELO_LOCAL.md): the arm carries the question, the
owner switches by saying so, and a Mac that is off never leaves the Visão mute."""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from apps.api.llm import get_llm_provider
from core import brain
from core.arm import local_llm
from infrastructure.database.models import ArmDevice, ArmLlmCall, Message, ModelUsage
from integrations.llm.base import ChatMessage, LLMError
from tests.fakes import FakeLLMProvider
from tests.integration.test_arm import _conversation, _pair
from tests.integration.test_mind import _owner_client


@pytest.fixture(autouse=True)
def _fresh_mode_cache():
    brain._cache.clear()
    yield
    brain._cache.clear()


def _factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def _offer(client, arm, model="qwen3:4b"):
    """The arm's long poll with no question waiting: the Mac now offers this model."""
    assert client.get(f"/arm/device/llm/next?model={model}", headers=arm).json() is None


def test_the_arm_answers_the_question_with_the_model_on_the_mac(client, db, engine):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    _offer(client, arm)
    provider = local_llm.LocalModelProvider(_factory(engine), timeout_seconds=5)
    answer: dict = {}

    def ask():
        answer["reply"] = provider.complete(
            [ChatMessage("system", "Você é o Visão."), ChatMessage("user", "oi")],
            max_output_tokens=200,
        )

    waiting = threading.Thread(target=ask)
    waiting.start()
    question = None
    for _ in range(50):
        question = client.get("/arm/device/llm/next?model=qwen3:4b", headers=arm).json()
        if question:
            break
    assert question["model"] == "qwen3:4b" and question["max_output_tokens"] == 200
    assert [m["role"] for m in question["messages"]] == ["system", "user"]
    done = client.post(
        f"/arm/device/llm/{question['id']}/result",
        json={"ok": True, "text": "Olá.", "input_tokens": 12, "output_tokens": 3},
        headers=arm,
    )
    assert done.status_code == 204
    waiting.join(5)
    reply = answer["reply"]
    assert reply.text == "Olá." and reply.provider == "local" and reply.model == "qwen3:4b"
    assert reply.cost_usd == 0 and reply.input_tokens == 12


def test_with_no_mac_offering_a_model_it_fails_at_once_so_the_cloud_takes_over(engine):
    provider = local_llm.LocalModelProvider(_factory(engine), timeout_seconds=5)
    with pytest.raises(LLMError) as raised:
        provider.complete([ChatMessage("user", "oi")], max_output_tokens=10)
    assert raised.value.kind == "network"


def test_a_mac_that_stopped_asking_is_no_longer_available(client, db):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    _offer(client, arm)
    assert local_llm.available(db).local_model == "qwen3:4b"
    device = db.scalars(select(ArmDevice)).one()
    device.local_seen_at = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()
    assert local_llm.available(db) is None


def test_another_owners_mac_cannot_answer_or_take_the_question(client, db, engine):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    _offer(client, arm)
    owner_id = db.scalars(select(ArmDevice)).one().owner_user_id
    call = ArmLlmCall(owner_user_id=owner_id, status="claimed", payload={"messages": []})
    db.add(call)
    db.commit()
    # A device that did not take it cannot answer it.
    response = client.post(
        f"/arm/device/llm/{call.id}/result", json={"ok": True, "text": "x"}, headers=arm
    )
    assert response.status_code == 404


def test_pictures_and_long_conversations_are_kept_within_what_a_small_model_reads():
    long = [ChatMessage("system", "regras")] + [
        ChatMessage("user" if i % 2 else "assistant", f"mensagem {i} " + "x" * 1000)
        for i in range(60)
    ]
    kept = local_llm.trim(long, 10_000)
    assert kept[0].content == "regras" and kept[-1] == long[-1]
    assert sum(len(m.content) for m in kept) <= 10_000
    assert len(kept) < len(long)


def _cloud_and_local():
    cloud = FakeLLMProvider(name="nuvem", reply_text="da nuvem")
    local = FakeLLMProvider(name="local", reply_text="do Mac")
    return cloud, local


def test_the_mode_orders_cloud_and_local_model(db, engine):
    cloud, local = _cloud_and_local()
    switch = brain.BrainProvider(cloud, local, _factory(engine))
    ask = [ChatMessage("user", "oi")]
    assert switch.complete(ask, max_output_tokens=10).text == "da nuvem"
    brain.set_mode(db, "local", actor_user_id=None, via="teste")
    db.commit()
    assert switch.complete(ask, max_output_tokens=10).text == "do Mac"
    # The Mac asleep: the cloud answers instead of nobody.
    local.fail_with = "network"
    assert switch.complete(ask, max_output_tokens=10).text == "da nuvem"
    brain.set_mode(db, "auto", actor_user_id=None, via="teste")
    db.commit()
    cloud.fail_with, local.fail_with = "quota_exhausted", None
    assert switch.complete(ask, max_output_tokens=10).text == "do Mac"


def test_background_work_pauses_in_local_mode_and_uses_only_the_cloud_otherwise(db, engine):
    cloud, local = _cloud_and_local()
    background = brain.BrainProvider(cloud, local, _factory(engine), background=True)
    ask = [ChatMessage("user", "resuma")]
    brain.set_mode(db, "auto", actor_user_id=None, via="teste")
    db.commit()
    assert background.complete(ask, max_output_tokens=10).text == "da nuvem"
    brain.set_mode(db, "local", actor_user_id=None, via="teste")
    db.commit()
    with pytest.raises(LLMError) as raised:
        background.complete(ask, max_output_tokens=10)
    assert raised.value.kind == "budget_denied"  # the worker defers the job


@pytest.mark.parametrize(
    ("text", "mode"),
    [
        ("usa o modelo local", "local"),
        ("Visão, passa pro local por favor", "local"),
        ("vamos usar o qwen", "local"),
        ("Volta pro Claude!", "nuvem"),
        ("troca para a nuvem", "nuvem"),
        ("modo automático", "auto"),
        ("/modelo local", "local"),
    ],
)
def test_short_orders_switch_the_model(text, mode):
    assert brain.parse_command(text) == brain.Command(mode)


@pytest.mark.parametrize(
    "text",
    [
        "o que é um modelo local?",
        "usa o qwen pra resumir esse texto",
        "usa a nuvem pra pesquisar isso",
        "o Claude é melhor que o Qwen em código, né",
    ],
)
def test_questions_and_longer_sentences_are_not_orders(text):
    assert brain.parse_command(text) is None


def test_asking_in_the_chat_switches_without_calling_any_model(client, db):
    _, owner = _owner_client(client, db)
    cloud = FakeLLMProvider(fail_with="quota_exhausted")
    client.app.dependency_overrides[get_llm_provider] = lambda: cloud
    chat = _conversation(client, owner)
    turn = client.post(
        f"/conversations/{chat}/messages", json={"content": "usa o modelo local"}, headers=owner
    )
    assert turn.status_code == 200, turn.text
    assert "modo local ligado" in turn.json()["assistant_message"]["content"]
    assert cloud.prompts == []  # recognized in code: works with the quota gone
    status = client.get("/arm/brain", headers=owner).json()
    assert status == {"mode": "local", "local_model": None, "mac_online": False}
    roles = [m.role for m in db.scalars(select(Message).order_by(Message.created_at))]
    assert roles[-2:] == ["user", "assistant"]


def test_the_owner_switches_in_ajustes_and_sees_the_mac(client, db):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    _offer(client, arm)
    switched = client.put("/arm/brain", json={"mode": "auto"}, headers=owner).json()
    assert switched == {"mode": "auto", "local_model": "qwen3:4b", "mac_online": True}
    assert client.put("/arm/brain", json={"mode": "turbo"}, headers=owner).status_code == 422


def test_a_reply_written_on_the_mac_is_marked_local(client, db):
    _, owner = _owner_client(client, db)
    local = FakeLLMProvider(name="local", model="qwen3:4b", reply_text="do Mac")
    client.app.dependency_overrides[get_llm_provider] = lambda: local
    chat = _conversation(client, owner)
    turn = client.post(f"/conversations/{chat}/messages", json={"content": "oi"}, headers=owner)
    assert turn.status_code == 200, turn.text
    assert turn.json()["assistant_message"]["local_model"] is True
    listed = client.get(f"/conversations/{chat}/messages", headers=owner).json()
    assert [m["local_model"] for m in listed if m["role"] == "assistant"][-1] is True
    assert db.scalars(select(ModelUsage.provider)).first() == "local"
