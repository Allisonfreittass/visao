import re

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.cli import create_user
from core.identity.genesis import run_genesis
from core.identity.naming import NamingDecision, record_naming_decision

PASSWORD = "senha-de-teste-longa"


def _auth_headers(client: TestClient, db: Session) -> dict[str, str]:
    create_user(db, "dono@exemplo.com", PASSWORD)
    token = client.post(
        "/auth/login", data={"username": "dono@exemplo.com", "password": PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_status_requires_auth(client: TestClient) -> None:
    assert client.get("/system/status").status_code == 401


def test_status_before_genesis(client: TestClient, db: Session) -> None:
    body = client.get("/system/status", headers=_auth_headers(client, db)).json()
    assert body == {"genesis_completed": False, "identity": None}


def test_status_after_genesis_has_null_name(client: TestClient, db: Session) -> None:
    headers = _auth_headers(client, db)
    identity = run_genesis(db).identity

    response = client.get("/system/status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["genesis_completed"] is True
    assert body["identity"]["internal_id"] == str(identity.id)
    assert body["identity"]["chosen_name"] is None
    assert body["identity"]["name_history"] == []
    assert body["identity"]["genesis"]["genesis_version"] == "2.1"
    # The project codename must not leak into the agent's identity.
    assert not re.search(r"(?i)\bvis(ã|a)o\b|\bvision\b", response.text)


def test_status_shows_name_history_after_choice(client: TestClient, db: Session) -> None:
    headers = _auth_headers(client, db)
    identity = run_genesis(db).identity
    for name in ("Primeiro", "Segundo"):
        record_naming_decision(
            db,
            identity,
            NamingDecision(
                action="choose",
                name=name,
                context_summary="teste",
                rationale_summary="teste",
                model_provider="test-provider",
                model_version="test-model-1",
            ),
        )

    body = client.get("/system/status", headers=headers).json()["identity"]

    assert body["internal_id"] == str(identity.id)
    assert body["chosen_name"] == "Segundo"
    assert [entry["name"] for entry in body["name_history"]] == ["Primeiro", "Segundo"]
