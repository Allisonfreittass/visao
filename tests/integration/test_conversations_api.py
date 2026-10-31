from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.cli import create_user
from apps.api.llm import get_llm_provider
from core.identity.genesis import get_identity, run_genesis
from infrastructure.database.models import Message, ModelUsage
from tests.fakes import FakeLLMProvider

PASSWORD = "senha-de-teste-longa"


@pytest.fixture
def fake_llm(client: TestClient) -> Iterator[FakeLLMProvider]:
    provider = FakeLLMProvider()
    client.app.dependency_overrides[get_llm_provider] = lambda: provider
    yield provider


def _login(client: TestClient, db: Session, email: str) -> dict[str, str]:
    create_user(db, email, PASSWORD)
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _new_conversation(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/conversations", headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def _say(client: TestClient, headers: dict[str, str], conversation_id: str, text: str):
    return client.post(
        f"/conversations/{conversation_id}/messages", headers=headers, json={"content": text}
    )


def test_conversation_requires_genesis(client: TestClient, db: Session) -> None:
    headers = _login(client, db, "a@exemplo.com")
    assert client.post("/conversations", headers=headers).status_code == 409


def test_unconfigured_llm_is_reported_not_faked(client: TestClient, db: Session) -> None:
    run_genesis(db)
    headers = _login(client, db, "a@exemplo.com")
    client.app.dependency_overrides[get_llm_provider] = lambda: None
    conversation_id = _new_conversation(client, headers)

    response = _say(client, headers, conversation_id, "oi")

    assert response.status_code == 503
    assert "VISION_LLM_API_KEY" in response.json()["detail"]
    assert db.scalars(select(Message)).all() == []


def test_conversation_works_without_name(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    headers = _login(client, db, "a@exemplo.com")
    conversation_id = _new_conversation(client, headers)

    response = _say(client, headers, conversation_id, "Qual é o seu nome?")

    assert response.status_code == 200
    body = response.json()
    assert body["assistant_message"]["content"] == "resposta de teste"
    assert Decimal(body["usage"]["cost_usd"]) == Decimal("0.002")  # 1000 in @1 + 500 out @2
    system = fake_llm.prompts[0][0]
    assert system.role == "system"
    assert "Nome pessoal: nenhum até o momento." in system.content
    assert get_identity(db).chosen_name is None

    history = client.get(f"/conversations/{conversation_id}/messages", headers=headers).json()
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_history_stays_inside_its_conversation(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    headers = _login(client, db, "a@exemplo.com")
    first = _new_conversation(client, headers)
    _say(client, headers, first, "segredo-da-primeira-conversa")
    _say(client, headers, first, "segunda mensagem")

    second = _new_conversation(client, headers)
    _say(client, headers, second, "você lembra de mim?")

    within_first = [m.content for m in fake_llm.prompts[1]]
    assert "segredo-da-primeira-conversa" in within_first
    second_prompt = " ".join(m.content for m in fake_llm.prompts[2])
    assert "segredo-da-primeira-conversa" not in second_prompt
    assert [m.role for m in fake_llm.prompts[2]] == ["system", "user"]


def test_other_users_cannot_see_or_use_conversation(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    owner = _login(client, db, "dono@exemplo.com")
    intruder = _login(client, db, "outro@exemplo.com")
    conversation_id = _new_conversation(client, owner)
    _say(client, owner, conversation_id, "privado")

    assert (
        client.get(f"/conversations/{conversation_id}/messages", headers=intruder).status_code
        == 404
    )
    assert _say(client, intruder, conversation_id, "oi").status_code == 404
    assert client.get("/conversations", headers=intruder).json() == []


def test_provider_failure_returns_no_answer(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    headers = _login(client, db, "a@exemplo.com")
    conversation_id = _new_conversation(client, headers)
    fake_llm.fail_with = "timeout"

    response = _say(client, headers, conversation_id, "oi")

    assert response.status_code == 502
    roles = [m.role for m in db.scalars(select(Message))]
    assert roles == ["user"]
    usage = db.scalar(select(ModelUsage))
    assert (usage.outcome, usage.error_kind) == ("error", "timeout")


def test_daily_budget_blocks_calls(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    headers = _login(client, db, "a@exemplo.com")
    conversation_id = _new_conversation(client, headers)
    db.add(
        ModelUsage(
            purpose="chat_reply",
            provider="fake-provider",
            model="fake-model",
            cost_usd=Decimal("1.50"),
            outcome="success",
            created_at=datetime.now(UTC),
        )
    )
    db.commit()

    response = _say(client, headers, conversation_id, "oi")

    assert response.status_code == 429
    assert "diário" in response.json()["detail"]
    assert fake_llm.prompts == []
    assert db.scalars(select(Message)).all() == []


def test_conversation_budget_blocks_calls(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    headers = _login(client, db, "a@exemplo.com")
    conversation_id = _new_conversation(client, headers)
    fake_llm.pricing = fake_llm.pricing.__class__(
        input_per_mtok=Decimal("300"), output_per_mtok=Decimal("0")
    )  # 1000 input tokens -> 0.30 USD, the whole conversation budget

    assert _say(client, headers, conversation_id, "primeira").status_code == 200
    response = _say(client, headers, conversation_id, "segunda")

    assert response.status_code == 429
    assert "conversa" in response.json()["detail"]
    assert len(fake_llm.prompts) == 1


def test_switching_llm_keeps_identity_and_history(client: TestClient, db: Session) -> None:
    identity_id = run_genesis(db).identity.id
    headers = _login(client, db, "a@exemplo.com")
    conversation_id = _new_conversation(client, headers)

    first = FakeLLMProvider(name="provider-a", model="model-a", reply_text="de A")
    client.app.dependency_overrides[get_llm_provider] = lambda: first
    _say(client, headers, conversation_id, "mensagem 1")

    second = FakeLLMProvider(name="provider-b", model="model-b", reply_text="de B")
    client.app.dependency_overrides[get_llm_provider] = lambda: second
    _say(client, headers, conversation_id, "mensagem 2")

    assert get_identity(db).id == identity_id
    assert "de A" in [m.content for m in second.prompts[0]]
    providers = sorted(u.provider for u in db.scalars(select(ModelUsage)))
    assert providers == ["provider-a", "provider-b"]
    history = client.get(f"/conversations/{conversation_id}/messages", headers=headers).json()
    assert [m["content"] for m in history] == ["mensagem 1", "de A", "mensagem 2", "de B"]


def test_message_validation(client: TestClient, db: Session, fake_llm: FakeLLMProvider) -> None:
    run_genesis(db)
    headers = _login(client, db, "a@exemplo.com")
    conversation_id = _new_conversation(client, headers)
    assert _say(client, headers, conversation_id, "").status_code == 422
    assert _say(client, headers, conversation_id, "x" * 8001).status_code == 422
