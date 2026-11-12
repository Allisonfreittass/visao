"""Changing email or password needs the current password and signs out every other session."""

import time

from apps.api.cli import create_user, set_email, set_password
from apps.api.security import issued_before_change

EMAIL = "dono@exemplo.com"
PASSWORD = "senha-antiga-bem-longa"


def _login(client, email=EMAIL, password=PASSWORD):
    response = client.post("/auth/login", data={"username": email, "password": password})
    return response


def _owner(client, db):
    create_user(db, EMAIL, PASSWORD)
    token = _login(client).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _wait_next_second():
    # Token issue times have one-second resolution; a change in the same second is ambiguous.
    time.sleep(1.05)


def test_password_change_needs_the_current_one_and_logs_out_old_tokens(client, db):
    old = _owner(client, db)
    wrong = {"current_password": "não-é-essa-senha", "new_password": "uma-senha-nova-longa"}
    assert client.post("/auth/password", json=wrong, headers=old).status_code == 403
    short = {"current_password": PASSWORD, "new_password": "curta"}
    assert client.post("/auth/password", json=short, headers=old).status_code == 422

    _wait_next_second()
    body = {"current_password": PASSWORD, "new_password": "uma-senha-nova-longa"}
    response = client.post("/auth/password", json=body, headers=old)
    assert response.status_code == 200
    fresh = {"Authorization": f"Bearer {response.json()['access_token']}"}

    assert client.get("/auth/me", headers=old).status_code == 401
    assert client.get("/auth/me", headers=fresh).status_code == 200
    assert _login(client).status_code == 401
    assert _login(client, password="uma-senha-nova-longa").status_code == 200


def test_email_change_moves_the_login_and_refuses_a_taken_email(client, db):
    old = _owner(client, db)
    create_user(db, "outra@exemplo.com", "outra-senha-bem-longa")
    taken = {"current_password": PASSWORD, "new_email": "outra@exemplo.com"}
    assert client.post("/auth/email", json=taken, headers=old).status_code == 409
    invalid = {"current_password": PASSWORD, "new_email": "não-é-email"}
    assert client.post("/auth/email", json=invalid, headers=old).status_code == 422

    _wait_next_second()
    body = {"current_password": PASSWORD, "new_email": "Novo@Exemplo.com"}
    response = client.post("/auth/email", json=body, headers=old)
    assert response.status_code == 200
    fresh = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/auth/me", headers=fresh).json()["email"] == "novo@exemplo.com"
    assert client.get("/auth/me", headers=old).status_code == 401
    assert _login(client, email="novo@exemplo.com").status_code == 200


def test_guessing_the_current_password_is_throttled(client, db):
    headers = _owner(client, db)
    wrong = {"current_password": "errada-errada-errada", "new_password": "uma-senha-nova-longa"}
    codes = [
        client.post("/auth/password", json=wrong, headers=headers).status_code for _ in range(9)
    ]
    assert codes[:8] == [403] * 8
    assert codes[8] == 429


def test_cli_changes_sign_out_existing_sessions(client, db):
    headers = _owner(client, db)
    _wait_next_second()
    set_password(db, EMAIL, "senha-trocada-pelo-terminal")
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert _login(client, password="senha-trocada-pelo-terminal").status_code == 200
    set_email(db, EMAIL, "terminal@exemplo.com")
    assert (
        _login(
            client, email="terminal@exemplo.com", password="senha-trocada-pelo-terminal"
        ).status_code
        == 200
    )


def test_tokens_from_before_a_change_are_rejected_and_later_ones_kept():
    from datetime import UTC, datetime

    changed = datetime(2026, 11, 12, 15, 0, 0, tzinfo=UTC)
    stamp = int(changed.timestamp())
    assert issued_before_change(stamp - 1, changed) is True
    assert issued_before_change(stamp, changed) is False
    assert issued_before_change(stamp - 999, None) is False
