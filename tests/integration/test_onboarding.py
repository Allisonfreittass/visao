"""First run: once per person, nothing kept without consent, and the owner's text never lost."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.cli import create_user
from apps.api.routes.onboarding import _flag_name
from core.mind import notes
from infrastructure.database.models import AuditLog, OwnerNote, SystemFlag, User

PASSWORD = "uma-senha-bem-longa"
ANSWERS = {
    "who": "Allison, em Salvador",
    "work": "Construo um agente pessoal",
    "goal": "Que me acompanhe nos projetos",
    "tone": "Direto, sem enrolação",
}


def login(client: TestClient, db: Session, email: str = "dono@example.com") -> dict[str, str]:
    create_user(db, email, PASSWORD)
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def consent(client: TestClient, headers: dict[str, str]) -> None:
    assert (
        client.put("/memory/settings", headers=headers, json={"enabled": True}).status_code == 200
    )


def owner(db: Session, email: str = "dono@example.com") -> User:
    db.expire_all()
    return db.scalar(select(User).where(User.email == email))


def note_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(OwnerNote)) or 0


def test_it_needs_a_login_and_starts_unfinished(client: TestClient, db: Session):
    assert client.get("/onboarding").status_code == 401
    assert client.post("/onboarding", json={"skip": True}).status_code == 401

    body = client.get("/onboarding", headers=login(client, db)).json()

    assert body["completed"] is False
    assert body["room"] == notes.LIMITS


def test_answers_become_the_notes_written_by_the_owner(client: TestClient, db: Session):
    headers = login(client, db)
    consent(client, headers)

    response = client.post("/onboarding", headers=headers, json={"answers": ANSWERS})

    assert response.json() == {
        "completed": True,
        "skipped": False,
        "saved": ["profile", "rules"],
        "discarded": False,
    }
    user = owner(db)
    profile = notes.latest(db, user.id, notes.PROFILE)
    rules = notes.latest(db, user.id, notes.RULES)
    assert profile.origin == rules.origin == "owner"
    assert ANSWERS["who"] in profile.content and ANSWERS["work"] in profile.content
    assert ANSWERS["goal"] in profile.content and ANSWERS["tone"] not in profile.content
    assert ANSWERS["tone"] in rules.content
    assert client.get("/onboarding", headers=headers).json()["completed"] is True
    mind = client.get("/mind", headers=headers).json()
    assert ANSWERS["who"] in mind["profile"]["content"]


def test_only_what_was_answered_is_written(client: TestClient, db: Session):
    headers = login(client, db)
    consent(client, headers)

    response = client.post(
        "/onboarding", headers=headers, json={"answers": {"tone": "  curto  ", "who": "   "}}
    )

    assert response.json()["saved"] == ["rules"]
    assert notes.current(db, owner(db).id, notes.PROFILE) == ""
    assert notes.current(db, owner(db).id, notes.RULES).endswith(": curto")


def test_without_consent_nothing_is_kept_and_the_response_says_so(client: TestClient, db: Session):
    headers = login(client, db)

    response = client.post("/onboarding", headers=headers, json={"answers": ANSWERS})

    assert response.json()["saved"] == []
    assert response.json()["discarded"] is True
    assert note_count(db) == 0
    stored = owner(db)
    flag = db.get(SystemFlag, _flag_name(stored.id))
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "onboarding.finished"))
    assert ANSWERS["who"] not in str(flag.value) and ANSWERS["who"] not in str(audit.details)
    assert client.get("/onboarding", headers=headers).json()["completed"] is True


def test_skip_finishes_and_never_comes_back(client: TestClient, db: Session):
    headers = login(client, db)
    consent(client, headers)

    response = client.post("/onboarding", headers=headers, json={"skip": True})

    assert response.json() == {
        "completed": True,
        "skipped": True,
        "saved": [],
        "discarded": False,
    }
    assert client.get("/onboarding", headers=headers).json()["completed"] is True
    assert note_count(db) == 0
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "onboarding.finished"))
    assert audit.outcome == "skipped"


def test_skip_with_answers_is_refused_instead_of_dropping_them(client: TestClient, db: Session):
    headers = login(client, db)

    response = client.post("/onboarding", headers=headers, json={"skip": True, "answers": ANSWERS})

    assert response.status_code == 422
    assert client.get("/onboarding", headers=headers).json()["completed"] is False


def test_an_existing_profile_is_kept_and_undo_brings_it_back(client: TestClient, db: Session):
    headers = login(client, db)
    consent(client, headers)
    user = owner(db)
    notes.write(db, user.id, notes.PROFILE, "Gosta de café forte.", "revisão")
    db.commit()

    client.post("/onboarding", headers=headers, json={"answers": ANSWERS})

    merged = notes.current(db, user.id, notes.PROFILE)
    assert merged.startswith("Gosta de café forte.\n") and ANSWERS["who"] in merged
    assert notes.latest(db, user.id, notes.PROFILE).version == 2
    client.post("/mind/notes/profile/undo", headers=headers)
    db.expire_all()
    assert notes.current(db, user.id, notes.PROFILE) == "Gosta de café forte."


def test_over_the_limit_is_refused_with_the_excess_and_can_be_retried(
    client: TestClient, db: Session
):
    headers = login(client, db)
    consent(client, headers)
    user = owner(db)
    notes.write(db, user.id, notes.PROFILE, "x" * 1390, "revisão")
    db.commit()
    assert client.get("/onboarding", headers=headers).json()["room"]["profile"] == 10

    refused = client.post("/onboarding", headers=headers, json={"answers": {"who": "y" * 50}})

    assert refused.status_code == 422
    excess = 1390 + 1 + len("Quem é: ") + 50 - 1400
    assert f"corte {excess} caracteres" in refused.json()["detail"]
    assert notes.latest(db, user.id, notes.PROFILE).version == 1
    assert client.get("/onboarding", headers=headers).json()["completed"] is False

    accepted = client.post("/onboarding", headers=headers, json={"answers": {"tone": "curto"}})
    assert accepted.json()["saved"] == ["rules"]


@pytest.mark.parametrize("text", ["minha senha é 1234", "sk-abcdefghijklmnop"])
def test_secrets_are_refused_before_reaching_the_prompt(client: TestClient, db: Session, text: str):
    headers = login(client, db)
    consent(client, headers)

    response = client.post("/onboarding", headers=headers, json={"answers": {"who": text}})

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert note_count(db) == 0
    assert client.get("/onboarding", headers=headers).json()["completed"] is False


def test_a_second_post_does_not_append_twice(client: TestClient, db: Session):
    headers = login(client, db)
    consent(client, headers)

    client.post("/onboarding", headers=headers, json={"answers": ANSWERS})
    again = client.post("/onboarding", headers=headers, json={"answers": ANSWERS})

    assert again.json()["saved"] == [] and again.json()["discarded"] is True
    assert note_count(db) == 2


def test_it_is_per_person(client: TestClient, db: Session):
    first = login(client, db)
    second = login(client, db, "outra@example.com")

    client.post("/onboarding", headers=first, json={"skip": True})

    assert client.get("/onboarding", headers=first).json()["completed"] is True
    assert client.get("/onboarding", headers=second).json()["completed"] is False
    assert len(_flag_name(owner(db).id)) <= 64


def test_an_unknown_answer_is_refused(client: TestClient, db: Session):
    headers = login(client, db)

    response = client.post("/onboarding", headers=headers, json={"answers": {"quem": "eu"}})

    assert response.status_code == 422
    assert client.get("/onboarding", headers=headers).json()["completed"] is False
