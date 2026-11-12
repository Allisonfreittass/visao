from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.cli import create_user
from apps.api.routes.auth import LOGIN_MAX_FAILURES, LoginThrottle

PASSWORD = "senha-de-teste-longa"


def _login(client: TestClient, email: str, password: str, ip: str | None = None):
    headers = {"CF-Connecting-IP": ip} if ip else {}
    return client.post(
        "/auth/login", data={"username": email, "password": password}, headers=headers
    )


def test_repeated_failures_for_one_email_are_throttled(client: TestClient, db: Session) -> None:
    create_user(db, "dono@exemplo.com", PASSWORD)
    for attempt in range(LOGIN_MAX_FAILURES):
        # Different addresses: the per-email window still applies.
        response = _login(client, "dono@exemplo.com", "errada-errada", ip=f"10.0.0.{attempt}")
        assert response.status_code == 401
    blocked = _login(client, "dono@exemplo.com", PASSWORD, ip="10.0.1.1")
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= 300
    # Another account from a fresh address is unaffected.
    create_user(db, "outra@exemplo.com", PASSWORD)
    assert _login(client, "outra@exemplo.com", PASSWORD, ip="10.0.2.1").status_code == 200


def test_repeated_failures_from_one_address_are_throttled(client: TestClient, db: Session) -> None:
    create_user(db, "dono@exemplo.com", PASSWORD)
    for attempt in range(LOGIN_MAX_FAILURES):
        assert _login(client, f"x{attempt}@exemplo.com", "errada", ip="10.9.9.9").status_code == 401
    assert _login(client, "dono@exemplo.com", PASSWORD, ip="10.9.9.9").status_code == 429
    assert _login(client, "dono@exemplo.com", PASSWORD, ip="10.9.9.8").status_code == 200


def test_success_resets_the_counters(client: TestClient, db: Session) -> None:
    create_user(db, "dono@exemplo.com", PASSWORD)
    for _ in range(LOGIN_MAX_FAILURES - 1):
        assert _login(client, "dono@exemplo.com", "errada").status_code == 401
    assert _login(client, "dono@exemplo.com", PASSWORD).status_code == 200
    for _ in range(LOGIN_MAX_FAILURES - 1):
        assert _login(client, "dono@exemplo.com", "errada").status_code == 401
    assert _login(client, "dono@exemplo.com", PASSWORD).status_code == 200


def test_window_slides() -> None:
    now = [1000.0]
    throttle = LoginThrottle(max_failures=2, window_seconds=60, clock=lambda: now[0])
    keys = ["email:a"]
    throttle.failure(keys)
    now[0] += 30
    throttle.failure(keys)
    assert throttle.retry_after(keys) == 30
    now[0] += 31
    assert throttle.retry_after(keys) is None
