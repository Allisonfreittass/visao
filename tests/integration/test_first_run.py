"""The first account made on a screen on the owner's machine (ADR-0027): only with the setting,
only from 127.0.0.1 without a proxy, only while nobody is signed up."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from apps.api.deps import get_session_factory
from apps.api.main import create_app
from apps.api.settings import get_settings
from core.identity.genesis import get_identity
from infrastructure.database.models import AuditLog, User

OWNER = {"email": "Dono@Exemplo.com", "password": "uma senha bem longa"}


def _client(engine, monkeypatch, *, enabled: bool, host: str) -> TestClient:
    monkeypatch.setenv("VISION_FIRST_RUN_SETUP", "true" if enabled else "false")
    get_settings.cache_clear()
    app = create_app()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.dependency_overrides[get_session_factory] = lambda: factory
    return TestClient(app, client=(host, 50000))


@pytest.fixture
def local(engine, monkeypatch) -> Iterator[TestClient]:
    with _client(engine, monkeypatch, enabled=True, host="127.0.0.1") as client:
        yield client
    get_settings.cache_clear()


def test_on_the_owner_machine_the_first_account_and_genesis_come_from_the_screen(local, db):
    assert local.get("/auth/first-run").json() == {"needed": True}
    reply = local.post("/auth/first-run", json=OWNER)
    assert reply.status_code == 200
    token = reply.json()["access_token"]
    me = local.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "dono@exemplo.com"
    assert get_identity(db) is not None
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "user.create"))
    assert audit.details == {"via": "first_run"}
    # Done once: the screen is gone and a second account cannot be made this way.
    assert local.get("/auth/first-run").json() == {"needed": False}
    again = local.post("/auth/first-run", json={**OWNER, "email": "outro@exemplo.com"})
    assert again.status_code == 404
    assert len(db.scalars(select(User)).all()) == 1


def test_a_short_password_is_refused_and_nothing_is_made(local, db):
    reply = local.post("/auth/first-run", json={**OWNER, "password": "curta"})
    assert reply.status_code == 422
    assert "12" in reply.json()["detail"]
    assert db.scalars(select(User)).all() == []


def test_through_a_proxy_it_does_not_exist(local, db):
    for header in ("X-Forwarded-For", "CF-Connecting-IP", "Forwarded", "X-Real-IP"):
        headers = {header: "203.0.113.9"}
        assert local.get("/auth/first-run", headers=headers).json() == {"needed": False}
        assert local.post("/auth/first-run", json=OWNER, headers=headers).status_code == 404
    assert db.scalars(select(User)).all() == []


@pytest.mark.parametrize(
    ("enabled", "host"), [(False, "127.0.0.1"), (True, "192.168.0.20"), (True, "203.0.113.9")]
)
def test_without_the_setting_or_from_another_machine_it_does_not_exist(
    engine, monkeypatch, db, enabled, host
):
    with _client(engine, monkeypatch, enabled=enabled, host=host) as client:
        assert client.get("/auth/first-run").json() == {"needed": False}
        assert client.post("/auth/first-run", json=OWNER).status_code == 404
    get_settings.cache_clear()
    assert db.scalars(select(User)).all() == []
