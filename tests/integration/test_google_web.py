"""The "Conectar" button on the hosted server: the owner's "Web application" client, Google's
answer back at /api/google/web/callback, and a sign-in that ends only in the browser that began
it, once, within 10 minutes. Google itself is replaced by fakes."""

from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from apps.api import google_web as web
from apps.api.routes import google as route
from apps.api.settings import Settings, get_settings
from core.google import account as accounts
from infrastructure.database.models import AuditLog, GoogleAccount
from integrations.google.client import SCOPES, Credentials, GoogleError
from tests.integration.test_google import KEY, FakeGoogle
from tests.integration.test_mind import _owner_client

ORIGIN = "https://visao.exemplo.com"
CLIENT = {"client_id": "123-web.apps.googleusercontent.com", "client_secret": "GOCSPX-segredo"}


@pytest.fixture(autouse=True)
def fresh():
    web.forget_all()
    yield
    web.forget_all()


@pytest.fixture
def owner(client, db):
    client.app.dependency_overrides[get_settings] = lambda: Settings(secret_key=KEY)
    return _owner_client(client, db)


@pytest.fixture
def google(monkeypatch):
    """Google's token endpoint and the first real call, both faked."""
    traded = []

    def exchange(code, client_id, client_secret, redirect, verifier):
        traded.append((code, client_id, client_secret, redirect, verifier))
        return "1//refresh-da-web", "", []

    monkeypatch.setattr(route.oauth, "exchange", exchange)
    monkeypatch.setattr(accounts, "GoogleClient", lambda creds: FakeGoogle())
    return traded


def begin(client, headers, **extra):
    started = client.post(
        "/google/web/start", headers=headers, json={"origin": ORIGIN, **CLIENT, **extra}
    )
    assert started.status_code == 200, started.text
    query = parse_qs(urlsplit(started.json()["url"]).query)
    cookie = started.cookies.get(web.COOKIE) or _cookie(started)
    return query, cookie, started


def _cookie(response):
    header = response.headers["set-cookie"]
    return header.split(";", 1)[0].split("=", 1)[1]


def back(client, state, cookie, **params):
    client.cookies.clear()
    query = {"state": state, "code": "4/codigo", **params}
    return client.get(
        "/google/web/callback",
        params=query,
        headers={"Cookie": f"{web.COOKIE}={cookie}"} if cookie else {},
        follow_redirects=False,
    )


def said(response) -> dict:
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert location.path == "/" and not location.netloc
    return {k: v[0] for k, v in parse_qs(location.query).items()}


def test_start_asks_google_for_the_same_scopes_and_sets_a_browser_cookie(client, owner):
    _, headers = owner
    query, cookie, started = begin(client, headers)
    assert query["redirect_uri"] == [f"{ORIGIN}/api/google/web/callback"]
    assert query["client_id"] == [CLIENT["client_id"]]
    assert query["scope"] == [" ".join(SCOPES)]
    assert query["code_challenge_method"] == ["S256"] and query["access_type"] == ["offline"]
    assert CLIENT["client_secret"] not in started.text
    set_cookie = started.headers["set-cookie"].lower()
    for part in ("httponly", "secure", "samesite=lax", "path=/api/google/web", "max-age=600"):
        assert part in set_cookie
    assert cookie and cookie not in query["state"][0]


def test_start_needs_the_owner_and_a_real_client(client, owner):
    _, headers = owner
    assert client.post("/google/web/start", json={"origin": ORIGIN, **CLIENT}).status_code == 401
    wrong_id = {**CLIENT, "client_id": "123-desktop.exemplo.com"}
    assert (
        client.post(
            "/google/web/start", headers=headers, json={"origin": ORIGIN, **wrong_id}
        ).status_code
        == 422
    )
    for origin in ("http://visao.exemplo.com", "https://x.com/caminho", "javascript:alert(1)"):
        refused = client.post(
            "/google/web/start", headers=headers, json={"origin": origin, **CLIENT}
        )
        assert refused.status_code == 422, origin
    assert web.redirect_uri("http://localhost:5173") == "http://localhost:5173" + web.CALLBACK_PATH


def test_the_return_connects_encrypted_and_lands_on_the_app(client, db, owner, google):
    user, headers = owner
    query, cookie, _ = begin(client, headers)
    answer = back(client, query["state"][0], cookie)
    assert said(answer) == {"google": "conectado"}
    assert answer.headers["cache-control"] == "no-store"
    assert f'{web.COOKIE}=""' in answer.headers["set-cookie"]
    code, client_id, secret, redirect, verifier = google[0]
    assert (code, client_id, secret) == ("4/codigo", CLIENT["client_id"], CLIENT["client_secret"])
    assert redirect == f"{ORIGIN}/api/google/web/callback" and len(verifier) >= 43
    row = db.scalar(select(GoogleAccount).where(GoogleAccount.owner_user_id == user.id))
    assert row.email == "dono@gmail.com"
    assert "1//refresh-da-web" not in row.secret and CLIENT["client_secret"] not in row.secret
    state = client.get("/google", headers=headers).json()
    assert state["connected"] is True and state["reconnect"] is False
    assert CLIENT["client_secret"] not in client.get("/google", headers=headers).text


def test_a_wrong_state_connects_nothing(client, db, owner, google):
    _, headers = owner
    _, cookie, _ = begin(client, headers)
    assert said(back(client, "um-state-inventado", cookie)) == {
        "google": "erro",
        "motivo": "vencido",
    }
    assert said(back(client, "", cookie))["motivo"] == "vencido"
    assert google == [] and db.scalar(select(GoogleAccount)) is None


def test_the_same_state_works_only_once(client, db, owner, google):
    _, headers = owner
    query, cookie, _ = begin(client, headers)
    assert said(back(client, query["state"][0], cookie))["google"] == "conectado"
    again = said(back(client, query["state"][0], cookie))
    assert again == {"google": "erro", "motivo": "vencido"} and len(google) == 1


def test_another_browser_cannot_finish_the_sign_in(client, db, owner, google):
    user, headers = owner
    query, _, _ = begin(client, headers)
    assert said(back(client, query["state"][0], None))["motivo"] == "navegador"
    # And the state is spent: the right browser cannot reuse it afterwards either.
    query2, cookie2, _ = begin(client, headers)
    assert said(back(client, query2["state"][0], "outro-cookie"))["motivo"] == "navegador"
    assert said(back(client, query2["state"][0], cookie2))["motivo"] == "vencido"
    assert google == [] and db.scalar(select(GoogleAccount)) is None
    failures = db.scalars(select(AuditLog).where(AuditLog.outcome == "failure")).all()
    # A spent state no longer knows whose it was: only the two known sign-ins are recorded.
    assert [f.details["reason"] for f in failures] == ["navegador", "navegador"]
    assert all(f.actor_user_id == user.id for f in failures)


def test_a_sign_in_expires_after_ten_minutes(owner):
    user, _ = owner
    url, nonce = web.start(user.id, CLIENT["client_id"], "s", ORIGIN, now=1000.0)
    state = parse_qs(urlsplit(url).query)["state"][0]
    with pytest.raises(web.FlowError) as late:
        web.take(state, nonce, now=1000.0 + web.FLOW_SECONDS + 1)
    assert late.value.reason == "vencido" and late.value.owner_id == user.id


def test_only_three_sign_ins_wait_per_owner(owner):
    user, _ = owner
    for _ in range(5):
        web.start(user.id, CLIENT["client_id"], "s", ORIGIN)
    assert len(web._flows) == web.MAX_FLOWS


def test_a_cancelled_or_refused_sign_in_says_why(client, db, owner, monkeypatch, google):
    _, headers = owner
    query, cookie, _ = begin(client, headers)
    assert said(back(client, query["state"][0], cookie, error="access_denied"))["motivo"] == (
        "recusado"
    )

    monkeypatch.setattr(route.oauth, "exchange", lambda *a: (None, "invalid_client", []))
    query, cookie, _ = begin(client, headers)
    assert said(back(client, query["state"][0], cookie))["motivo"] == "troca"

    def refuses(creds):
        fake = FakeGoogle()
        fake.address = lambda: (_ for _ in ()).throw(GoogleError("revoked", "sem acesso"))
        return fake

    monkeypatch.setattr(route.oauth, "exchange", lambda *a: ("1//r", "", []))
    monkeypatch.setattr(accounts, "GoogleClient", refuses)
    query, cookie, _ = begin(client, headers)
    assert said(back(client, query["state"][0], cookie))["motivo"] == "google"
    assert db.scalar(select(GoogleAccount)) is None


def test_unticked_permissions_are_named_on_the_way_back(client, owner, monkeypatch, google):
    _, headers = owner
    monkeypatch.setattr(route.oauth, "exchange", lambda *a: ("1//r", "", ["gmail.send"]))
    query, cookie, _ = begin(client, headers)
    assert said(back(client, query["state"][0], cookie)) == {
        "google": "conectado",
        "faltou": "gmail.send",
    }


def test_a_changed_server_key_asks_to_connect_again(client, db, owner, google):
    user, headers = owner
    query, cookie, _ = begin(client, headers)
    back(client, query["state"][0], cookie)
    # As if VISION_SECRET_KEY changed: the kept connection was sealed with another key.
    row = db.scalar(select(GoogleAccount).where(GoogleAccount.owner_user_id == user.id))
    creds = Credentials(CLIENT["client_id"], CLIENT["client_secret"], "1//refresh-da-web")
    row.secret = accounts._seal(creds, "uma-chave-antiga-com-mais-de-32-caracteres!!")
    db.commit()
    state = client.get("/google", headers=headers).json()
    assert state["connected"] is True and state["reconnect"] is True
    # Connecting again from the screen replaces it with one this server can open.
    query, cookie, _ = begin(client, headers)
    assert said(back(client, query["state"][0], cookie))["google"] == "conectado"
    assert client.get("/google", headers=headers).json()["reconnect"] is False
