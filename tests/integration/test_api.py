import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.cli import create_user
from infrastructure.database.models import AuditLog

PASSWORD = "senha-de-teste-longa"


def _login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_ready_with_database(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "up"


def test_login_and_me(client: TestClient, db: Session) -> None:
    user = create_user(db, "Pessoa@Exemplo.com", PASSWORD)
    assert user.email == "pessoa@exemplo.com"

    response = _login(client, "pessoa@exemplo.com", PASSWORD)
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "pessoa@exemplo.com"

    actions = db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)).all()
    assert actions == ["user.create", "auth.login"]


def test_login_wrong_password_is_audited_without_secret(client: TestClient, db: Session) -> None:
    create_user(db, "a@exemplo.com", PASSWORD)
    response = _login(client, "a@exemplo.com", "errada-errada-errada")
    assert response.status_code == 401

    denied = db.scalar(select(AuditLog).where(AuditLog.outcome == "denied"))
    assert denied is not None
    assert "errada" not in str(denied.details)


def test_login_unknown_user(client: TestClient) -> None:
    assert _login(client, "ninguem@exemplo.com", PASSWORD).status_code == 401


def test_me_requires_token(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    bad = client.get("/auth/me", headers={"Authorization": "Bearer lixo"})
    assert bad.status_code == 401


def test_inactive_user_cannot_login(client: TestClient, db: Session) -> None:
    user = create_user(db, "b@exemplo.com", PASSWORD)
    user.is_active = False
    db.commit()
    assert _login(client, "b@exemplo.com", PASSWORD).status_code == 401


@pytest.mark.parametrize(
    ("email", "password"),
    [("nao-e-email", PASSWORD), ("c@exemplo.com", "curta")],
)
def test_create_user_validation(db: Session, email: str, password: str) -> None:
    with pytest.raises(ValueError):
        create_user(db, email, password)


def test_create_user_duplicate(db: Session) -> None:
    create_user(db, "d@exemplo.com", PASSWORD)
    with pytest.raises(ValueError):
        create_user(db, "D@exemplo.com", PASSWORD)
