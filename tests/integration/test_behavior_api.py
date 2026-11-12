"""Phase 6 acceptance through the API: changes observable, attributable and reversible."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.cli import create_user
from apps.api.llm import get_llm_provider
from core.identity.genesis import run_genesis
from infrastructure.database.models import BehaviorObservation
from tests.fakes import FakeLLMProvider

PASSWORD = "senha-de-teste-longa"


@pytest.fixture
def llm(client: TestClient) -> Iterator[FakeLLMProvider]:
    provider = FakeLLMProvider(reply_text="Uma resposta. Com duas frases.")
    client.app.dependency_overrides[get_llm_provider] = lambda: provider
    yield provider


def _login(client: TestClient, db: Session, email: str = "a@exemplo.com") -> dict[str, str]:
    create_user(db, email, PASSWORD)
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _reply(client: TestClient, headers: dict[str, str], conversation: str) -> dict:
    response = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": "Explique X"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_feedback_adapts_reversibly_and_attributably(client, db, llm) -> None:
    run_genesis(db)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]

    first = _reply(client, headers, conversation)
    assert "Ajustes de comunicação" not in llm.prompts[-1][0].content  # baseline: nothing added

    for _ in range(2):
        out = client.post(
            f"/messages/{first['assistant_message']['id']}/feedback",
            headers=headers,
            json={"rating": -1, "tags": ["muito longo"]},
        ).json()
        assert out["state_changed"] is False
    third = client.post(
        f"/messages/{first['assistant_message']['id']}/feedback",
        headers=headers,
        json={"rating": -1, "tags": ["muito longo"]},
    ).json()
    assert third == {**third, "state_version": 1, "state_changed": True}

    _reply(client, headers, conversation)
    system = llm.prompts[-1][0].content
    assert "versão 1, revertíveis" in system and "no máximo 3 frases" in system

    state = client.get("/behavior/state", headers=headers).json()
    assert state["history"][0]["cause"] == "feedback"
    assert len(state["history"][0]["evidence"]["feedback_ids"]) == 3

    reverted = client.post("/behavior/state/revert", headers=headers, json={"to_version": 0})
    assert reverted.json()["current_version"] == 2
    assert reverted.json()["prompt_adjustments"] == []
    _reply(client, headers, conversation)
    assert "Ajustes de comunicação" not in llm.prompts[-1][0].content

    # Every reply was measured under the version in force at the time.
    versions = [
        o.state_version
        for o in db.scalars(select(BehaviorObservation).order_by(BehaviorObservation.created_at))
    ]
    assert versions == [0, 1, 2]
    report = client.get("/behavior/report", headers=headers).json()
    assert report["observations"] == 3
    assert set(report["by_state_version"]) == {"0", "1", "2"}


def test_feedback_only_on_own_replies(client, db, llm) -> None:
    run_genesis(db)
    owner = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    conversation = client.post("/conversations", headers=owner).json()["id"]
    turn = _reply(client, owner, conversation)

    stranger = client.post(
        f"/messages/{turn['assistant_message']['id']}/feedback",
        headers=other,
        json={"rating": 1},
    )
    assert stranger.status_code == 404
    on_user_message = client.post(
        f"/messages/{turn['user_message']['id']}/feedback", headers=owner, json={"rating": 1}
    )
    assert on_user_message.status_code == 422
    bad_tag = client.post(
        f"/messages/{turn['assistant_message']['id']}/feedback",
        headers=owner,
        json={"rating": 1, "tags": ["seja engraçado"]},
    )
    assert bad_tag.status_code == 422


def test_reflection_endpoint_and_lessons(client, db, llm) -> None:
    run_genesis(db)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    turn = _reply(client, headers, conversation)
    client.post(
        f"/messages/{turn['assistant_message']['id']}/feedback",
        headers=headers,
        json={"rating": -1, "tags": ["faltou fonte"]},
    )
    llm.reply_text = (
        '{"lessons": [{"scope": "research", "observation": "faltou fonte", "evidence": ["e1"],'
        ' "lesson": "Citar a origem ao afirmar fatos", "confidence": 0.7}]}'
    )

    result = client.post(f"/conversations/{conversation}/reflect", headers=headers).json()

    assert result["created"] == 1
    lessons = client.get("/lessons", headers=headers).json()
    assert lessons[0]["status"] == "PROVISIONAL"
    retire = client.post(f"/lessons/{lessons[0]['id']}/retire", headers=headers)
    assert retire.status_code == 204
    assert client.get("/lessons", headers=headers).json()[0]["status"] == "RETIRED"


def test_reflection_respects_the_autonomy_budget(client, db, llm) -> None:
    from apps.api.settings import Settings, get_settings
    from infrastructure.database.models import Conversation

    run_genesis(db)
    headers = _login(client, db)
    client.app.dependency_overrides[get_settings] = lambda: Settings(autonomy_llm_calls_per_day=0)
    first = client.post("/conversations", headers=headers).json()["id"]
    turn = _reply(client, headers, first)
    client.post(
        f"/messages/{turn['assistant_message']['id']}/feedback",
        headers=headers,
        json={"rating": -1, "tags": ["faltou fonte"]},
    )
    calls = len(llm.prompts)

    result = client.post(f"/conversations/{first}/reflect", headers=headers).json()
    assert result["skipped_reason"] == "autonomy_budget" and result["created"] == 0
    # Opening a new conversation schedules a background reflection on the previous one.
    client.post("/conversations", headers=headers)
    assert len(llm.prompts) == calls
    db.expire_all()
    assert db.get(Conversation, __import__("uuid").UUID(first)).last_reflected_at is None
