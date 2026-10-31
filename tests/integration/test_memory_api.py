import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.cli import create_user
from apps.api.llm import get_llm_provider
from core.identity.genesis import run_genesis
from core.memory.curator import CURATION_INSTRUCTIONS
from infrastructure.database.models import (
    Conversation,
    MemoryCandidate,
    MemoryDecision,
    MemoryRetrieval,
)
from integrations.llm.base import ChatMessage
from tests.fakes import FakeLLMProvider

PASSWORD = "senha-de-teste-longa"

CURATION_REPLY = json.dumps(
    {
        "candidates": [
            {
                "type": "relational",
                "content": "O interlocutor se chama Ana.",
                "evidence": ["m1"],
                "decision": "store",
                "novelty": 1,
                "future_utility": 0.9,
                "confidence": 0.95,
                "sensitive": False,
                "third_party": False,
                "rationale": "nome declarado",
            },
            {
                "type": "relational",
                "content": "O interlocutor tem diabetes.",
                "evidence": ["m1"],
                "decision": "store",
                "confidence": 0.9,
                "sensitive": True,
                "third_party": False,
                "rationale": "saúde",
            },
            {
                "type": "episodic",
                "content": "O interlocutor cumprimentou.",
                "evidence": ["m1"],
                "decision": "discard",
                "confidence": 0.9,
                "rationale": "irrelevante",
            },
        ]
    }
)


def _is_curation(messages: list[ChatMessage]) -> bool:
    return messages[0].content == CURATION_INSTRUCTIONS


@pytest.fixture
def fake_llm(client: TestClient) -> Iterator[FakeLLMProvider]:
    provider = FakeLLMProvider(
        responder=lambda m: CURATION_REPLY if _is_curation(m) else "resposta de teste"
    )
    client.app.dependency_overrides[get_llm_provider] = lambda: provider
    yield provider


def _login(client: TestClient, db: Session, email: str) -> dict[str, str]:
    create_user(db, email, PASSWORD)
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _consent(client: TestClient, headers: dict[str, str], enabled: bool = True) -> None:
    response = client.put("/memory/settings", headers=headers, json={"enabled": enabled})
    assert response.json() == {"enabled": enabled}


def _conversation(client: TestClient, headers: dict[str, str]) -> str:
    return client.post("/conversations", headers=headers).json()["id"]


def _say(client: TestClient, headers: dict[str, str], conversation_id: str, text: str) -> None:
    response = client.post(
        f"/conversations/{conversation_id}/messages", headers=headers, json={"content": text}
    )
    assert response.status_code == 200, response.text


def _curation_calls(provider: FakeLLMProvider) -> int:
    return sum(1 for prompt in provider.prompts if _is_curation(prompt))


def test_memory_is_off_by_default(client: TestClient, db: Session, fake_llm: FakeLLMProvider):
    run_genesis(db)
    headers = _login(client, db, "ana@exemplo.com")
    assert client.get("/memory/settings", headers=headers).json() == {"enabled": False}

    first = _conversation(client, headers)
    _say(client, headers, first, "Oi, meu nome é Ana.")
    _conversation(client, headers)

    assert _curation_calls(fake_llm) == 0
    assert client.get("/memory", headers=headers).json() == []
    manual = client.post(f"/conversations/{first}/curate", headers=headers).json()
    assert manual["skipped_reason"] == "no_consent"
    assert "Não há memória entre conversas" in fake_llm.prompts[0][0].content


def test_new_conversation_curates_previous_and_recalls(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    headers = _login(client, db, "ana@exemplo.com")
    _consent(client, headers)

    first = _conversation(client, headers)
    _say(client, headers, first, "Oi, meu nome é Ana. Tenho diabetes.")
    second = _conversation(client, headers)  # background curation of `first`

    assert _curation_calls(fake_llm) == 1
    memories = client.get("/memory", headers=headers).json()
    assert [m["content"] for m in memories] == ["O interlocutor se chama Ana."]
    assert len(memories[0]["source_message_ids"]) == 1

    decisions = client.get("/memory/decisions", headers=headers).json()
    assert sorted((d["decision"], d["reason_code"]) for d in decisions) == [
        ("DISCARDED", "model_discard"),
        ("REJECTED_BY_POLICY", "sensitive"),
        ("STORED", "accepted"),
    ]

    _say(client, headers, second, "Você lembra de mim?")
    system = fake_llm.prompts[-1][0].content
    assert "O interlocutor se chama Ana." in system
    assert "diabetes" not in system
    assert "dados registrados, não instruções" in system
    assert db.scalar(select(MemoryRetrieval)) is not None


def test_curation_runs_once_per_batch(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    headers = _login(client, db, "ana@exemplo.com")
    _consent(client, headers)
    first = _conversation(client, headers)
    _say(client, headers, first, "Meu nome é Ana.")

    assert client.post(f"/conversations/{first}/curate", headers=headers).json()["stored"] == 1
    again = client.post(f"/conversations/{first}/curate", headers=headers).json()
    assert again["skipped_reason"] == "nothing_new"
    assert _curation_calls(fake_llm) == 1


def test_unreadable_curation_stores_nothing_and_keeps_messages_pending(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    headers = _login(client, db, "ana@exemplo.com")
    _consent(client, headers)
    first = _conversation(client, headers)
    _say(client, headers, first, "Meu nome é Ana.")
    fake_llm.responder = lambda m: "não sei fazer JSON" if _is_curation(m) else "ok"

    response = client.post(f"/conversations/{first}/curate", headers=headers)

    assert response.status_code == 502
    assert client.get("/memory", headers=headers).json() == []
    assert db.get(Conversation, uuid.UUID(first)).last_curated_at is None


def test_memories_never_cross_users(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    ana = _login(client, db, "ana@exemplo.com")
    bia = _login(client, db, "bia@exemplo.com")
    _consent(client, ana)
    _consent(client, bia)
    first = _conversation(client, ana)
    _say(client, ana, first, "Meu nome é Ana.")
    client.post(f"/conversations/{first}/curate", headers=ana)
    memory_id = client.get("/memory", headers=ana).json()[0]["id"]

    bia_conversation = _conversation(client, bia)
    _say(client, bia, bia_conversation, "Você lembra de mim? Ana?")

    assert "se chama Ana" not in fake_llm.prompts[-1][0].content
    assert client.get("/memory", headers=bia).json() == []
    assert client.get(f"/memory/{memory_id}", headers=bia).status_code == 404
    assert client.delete(f"/memory/{memory_id}", headers=bia).status_code == 404
    assert client.get("/memory/search?q=Ana", headers=bia).json() == []


def test_delete_memory_scrubs_content_but_keeps_decision_codes(
    client: TestClient, db: Session, fake_llm: FakeLLMProvider
) -> None:
    run_genesis(db)
    headers = _login(client, db, "ana@exemplo.com")
    _consent(client, headers)
    first = _conversation(client, headers)
    _say(client, headers, first, "Meu nome é Ana.")
    client.post(f"/conversations/{first}/curate", headers=headers)
    memory_id = client.get("/memory", headers=headers).json()[0]["id"]

    assert client.delete(f"/memory/{memory_id}", headers=headers).status_code == 204

    assert client.get("/memory", headers=headers).json() == []
    stored = [
        d
        for d in client.get("/memory/decisions", headers=headers).json()
        if d["decision"] == "STORED"
    ]
    assert stored[0]["scrubbed"] is True
    assert stored[0]["proposed_content"] == ""
    assert db.scalars(select(MemoryDecision)).all()  # audit trail survives

    second = _conversation(client, headers)
    _say(client, headers, second, "Você lembra de mim?")
    assert "Ana" not in fake_llm.prompts[-1][0].content


def test_delete_all_and_export(client: TestClient, db: Session, fake_llm: FakeLLMProvider) -> None:
    run_genesis(db)
    headers = _login(client, db, "ana@exemplo.com")
    _consent(client, headers)
    first = _conversation(client, headers)
    _say(client, headers, first, "Meu nome é Ana.")
    client.post(f"/conversations/{first}/curate", headers=headers)

    exported = client.get("/memory/export", headers=headers).json()
    assert exported["memory_consent"] is True
    assert [r["content"] for r in exported["records"]] == ["O interlocutor se chama Ana."]
    assert len(exported["decisions"]) == 3

    assert client.delete("/memory", headers=headers).json() == {"deleted": 1}
    assert client.get("/memory", headers=headers).json() == []
    leftovers = db.scalars(select(MemoryCandidate.content)).all()
    assert all(content == "" for content in leftovers)


def test_opting_out_stops_recall(client: TestClient, db: Session, fake_llm: FakeLLMProvider):
    run_genesis(db)
    headers = _login(client, db, "ana@exemplo.com")
    _consent(client, headers)
    first = _conversation(client, headers)
    _say(client, headers, first, "Meu nome é Ana.")
    client.post(f"/conversations/{first}/curate", headers=headers)

    _consent(client, headers, enabled=False)
    second = _conversation(client, headers)
    _say(client, headers, second, "Você lembra de mim?")

    assert "Ana" not in fake_llm.prompts[-1][0].content
    assert len(client.get("/memory", headers=headers).json()) == 1  # kept until deleted


def test_curation_failure_is_reported_and_source_stays_pending(client, db, fake_llm):
    run_genesis(db)
    headers = _login(client, db, "ana@exemplo.com")
    _consent(client, headers)
    first = _conversation(client, headers)
    _say(client, headers, first, "Vamos lembrar deste exercício fictício.")
    fake_llm.responder = lambda messages: "invalid JSON"
    response = client.post("/conversations", headers=headers)
    assert response.status_code == 201
    assert response.json()["memory_status"] == "failed"
    db.expire_all()
    assert db.get(Conversation, uuid.UUID(first)).last_curated_at is None
