"""The "Conectar com o Google" button of the Mac app: only from the owner's own machine, the server
opens the sign-in, and Google's return to 127.0.0.1 keeps the connection."""

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from apps.api.deps import get_session_factory
from apps.api.main import create_app
from apps.api.routes import google as route
from infrastructure.database.models import GoogleAccount
from tests.integration.test_mind import _owner_client

CLIENT = {
    "installed": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "s3cr3t"}
}


@pytest.fixture
def local(engine):
    """The app as the Mac app reaches it: from 127.0.0.1, at http://127.0.0.1:8000."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as c:
        yield c


@pytest.fixture
def browser(monkeypatch):
    opened = []
    monkeypatch.setattr(route.webbrowser, "open", lambda url: opened.append(url) or True)
    return opened


def test_the_button_shows_only_on_the_owners_machine(client, local, db):
    _, headers = _owner_client(local, db)
    assert local.get("/google", headers=headers).json()["connect_here"] is True
    # The hosted server (behind a proxy, or any other client) keeps the terminal command.
    behind = local.get("/google", headers={**headers, "X-Forwarded-For": "200.1.2.3"}).json()
    assert behind["connect_here"] is False
    assert client.get("/google", headers=headers).json()["connect_here"] is False
    refused = client.post("/google/start", json={"client": CLIENT}, headers=headers)
    assert refused.status_code == 409


def test_the_button_opens_the_sign_in_and_the_return_connects(local, db, browser, monkeypatch):
    owner, headers = _owner_client(local, db)
    started = local.post("/google/start", json={"client": CLIENT}, headers=headers)
    assert started.status_code == 200 and started.json()["opened"] is True
    query = parse_qs(urlsplit(browser[0]).query)
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/google/callback"]
    assert query["client_id"] == [CLIENT["installed"]["client_id"]]
    assert query["code_challenge_method"] == ["S256"]

    traded = []
    monkeypatch.setattr(
        route.oauth,
        "exchange",
        lambda code, cid, secret, redirect, verifier: (
            traded.append((code, cid, secret, redirect)) or ("refresh-token-xyz", "", [])
        ),
    )

    def connect(session, owner_id, credentials, secret_key):
        session.add(GoogleAccount(owner_user_id=owner_id, email="dono@gmail.com", secret="x"))
        assert credentials.refresh_token == "refresh-token-xyz"

    monkeypatch.setattr(route.accounts, "connect", connect)
    back = local.get(f"/google/callback?state={query['state'][0]}&code=abc")
    assert back.status_code == 200 and "Google conectado" in back.text
    assert traded == [("abc", CLIENT["installed"]["client_id"], "s3cr3t", query["redirect_uri"][0])]
    assert db.query(GoogleAccount).filter_by(owner_user_id=owner.id).count() == 1
    # The same return can never be used twice.
    again = local.get(f"/google/callback?state={query['state'][0]}&code=abc")
    assert again.status_code == 400


def test_a_return_that_was_not_started_here_is_refused(local, db):
    back = local.get("/google/callback?state=inventado&code=abc")
    assert back.status_code == 400 and "não começou aqui" in back.text


def test_a_wrong_file_says_so(local, db, browser):
    _, headers = _owner_client(local, db)
    web_client = {"web": CLIENT["installed"]}
    wrong = local.post("/google/start", json={"client": web_client}, headers=headers)
    assert wrong.status_code == 422 and "App para computador" in wrong.json()["detail"]
    assert local.post("/google/start", json={}, headers=headers).status_code == 422
    assert browser == []


def test_the_access_log_never_shows_the_sign_in_code():
    import logging

    from apps.api.main import _HIDE_SIGN_IN_CODE

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5", "GET", "/google/callback?state=abc&code=4/0secret", "1.1", 200),
        None,
    )
    _HIDE_SIGN_IN_CODE.filter(record)
    assert "secret" not in record.getMessage() and "/google/callback?…" in record.getMessage()
