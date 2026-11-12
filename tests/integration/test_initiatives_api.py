"""Phase 5 acceptance: an initiative triggered by a real event, run only after approval and within
permissions, ending in a notification only when it found something useful."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.cli import create_user
from apps.api.llm import get_llm_provider
from apps.api.search import get_search_provider
from apps.api.settings import Settings, get_settings
from apps.worker.handlers import research_followup_handler
from apps.worker.runner import run_once
from core.curiosity.engine import ASSESSMENT_INSTRUCTIONS
from core.goals.followup import SUMMARY_INSTRUCTIONS
from core.identity.genesis import run_genesis
from infrastructure.database.models import Goal, KnowledgeGap, Notification, ScheduledJob
from integrations.llm.base import ChatMessage
from integrations.search.base import SearchResult
from tests.fakes import FakeLLMProvider

PASSWORD = "senha-de-teste-longa"
ASSESSMENT = {
    "gap": True,
    "trigger": "uncertainty",
    "depends_on": "public_fact",
    "question": "Qual é a capital da Austrália?",
    "hypothesis": "Camberra",
    "search_query": "capital da Austrália",
    "uncertainty": 0.7,
    "expected_value": 0.8,
    "urgency": 0.3,
    "risk": 0.0,
}
CANBERRA = SearchResult(
    url="https://pt.wikipedia.org/wiki/Camberra",
    title="Camberra",
    snippet="Camberra é a capital da Austrália.",
    source="Wikipédia (pt)",
    retrieved_at=datetime.now(UTC),
)


class SwitchableSearch:
    name = "fake-search"

    def __init__(self) -> None:
        self.results: list[SearchResult] = []

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        return self.results[:max_results]


@pytest.fixture
def world(client: TestClient, engine: Engine) -> Iterator[dict]:
    state = {"answered": True}
    search = SwitchableSearch()

    def responder(messages: list[ChatMessage]) -> str:
        if messages[0].content == ASSESSMENT_INSTRUCTIONS:
            return json.dumps(ASSESSMENT)
        if messages[0].content == SUMMARY_INSTRUCTIONS:
            return json.dumps(
                {
                    "answered": state["answered"],
                    "summary": f"A capital é Camberra ({CANBERRA.url}).",
                    "uncertain": "",
                }
            )
        return "resposta de teste"

    llm = FakeLLMProvider(responder=responder)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_search_provider] = lambda: search
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    handlers = {"research_followup": research_followup_handler(Settings(), llm, search)}
    yield {"state": state, "search": search, "factory": factory, "handlers": handlers}


def _login(client: TestClient, db: Session, email: str = "a@exemplo.com") -> dict[str, str]:
    # No quiet hours, so notifications are visible immediately in the test.
    user = create_user(db, email, PASSWORD)
    user.quiet_start = user.quiet_end = "00:00"
    db.commit()
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _inconclusive_turn(client: TestClient, headers: dict[str, str]) -> dict:
    conversation = client.post("/conversations", headers=headers).json()["id"]
    response = client.post(
        f"/conversations/{conversation}/messages",
        headers=headers,
        json={"content": "Qual é a capital da Austrália?"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_unanswered_question_becomes_initiative_after_approval(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)

    body = _inconclusive_turn(client, headers)
    assert body["curiosity"]["status"] == "INCONCLUSIVE"
    goal_id = body["curiosity"]["proposed_goal_id"]
    assert goal_id is not None

    # Nothing runs before approval.
    assert client.get("/initiatives", headers=headers).json() == []
    approvals = client.get("/approvals", headers=headers).json()
    assert [g["id"] for g in approvals] == [goal_id]
    assert approvals[0]["required_permissions"] == ["llm", "notify", "web_research"]

    assert client.post(f"/goals/{goal_id}/approve", headers=headers).status_code == 200
    initiatives = client.get("/initiatives", headers=headers).json()
    assert [(i["kind"], i["status"]) for i in initiatives] == [("research_followup", "PENDING")]
    assert "Meta aprovada" in initiatives[0]["reason"]

    world["search"].results = [CANBERRA]  # the source exists now
    assert run_once(world["factory"], world["handlers"], "w") == "done"

    notifications = client.get("/notifications", headers=headers).json()
    assert len(notifications) == 1
    assert "Qual é a capital da Austrália?" in notifications[0]["title"]
    assert CANBERRA.url in notifications[0]["body"]

    goal = client.get("/goals", headers=headers).json()[0]
    assert goal["status"] == "COMPLETED"
    assert [e["to_status"] for e in goal["history"]] == [
        "PROPOSED",
        "EVALUATED",
        "APPROVED",
        "ACTIVE",
        "COMPLETED",
    ]
    assert goal["evidence"]["sources"] == [CANBERRA.url]
    assert db.scalar(select(KnowledgeGap.status)) == "RESEARCHED"


def test_irrelevant_sources_end_without_notification(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    goal_id = _inconclusive_turn(client, headers)["curiosity"]["proposed_goal_id"]
    client.post(f"/goals/{goal_id}/approve", headers=headers)
    world["search"].results = [CANBERRA]
    world["state"]["answered"] = False

    assert run_once(world["factory"], world["handlers"], "w") == "done"

    assert client.get("/notifications", headers=headers).json() == []
    goal = client.get("/goals", headers=headers).json()[0]
    assert goal["status"] == "FAILED"
    assert goal["history"][-1]["reason"] == "fontes não respondem à pergunta"


def test_rejected_proposal_never_runs(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    goal_id = _inconclusive_turn(client, headers)["curiosity"]["proposed_goal_id"]

    rejected = client.post(f"/goals/{goal_id}/reject", headers=headers, json={"reason": "não"})
    assert rejected.json()["status"] == "REJECTED"
    assert client.get("/initiatives", headers=headers).json() == []
    assert run_once(world["factory"], world["handlers"], "w") == "idle"
    assert client.post(f"/goals/{goal_id}/approve", headers=headers).status_code == 409


def test_paused_autonomy_proposes_and_runs_nothing(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    goal_id = _inconclusive_turn(client, headers)["curiosity"]["proposed_goal_id"]
    client.post(f"/goals/{goal_id}/approve", headers=headers)

    paused = client.put("/system/autonomy", headers=headers, json={"paused": True, "reason": "x"})
    assert paused.json() == {"paused": True}
    assert run_once(world["factory"], world["handlers"], "w") == "paused"

    body = _inconclusive_turn(client, headers)
    assert body["curiosity"]["proposed_goal_id"] is None
    assert len(db.scalars(select(Goal)).all()) == 1
    assert db.scalars(select(Notification)).all() == []


def test_goals_are_private_to_their_owner(client, db, world) -> None:
    run_genesis(db)
    owner = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    goal_id = _inconclusive_turn(client, owner)["curiosity"]["proposed_goal_id"]

    assert client.get("/approvals", headers=other).json() == []
    assert client.post(f"/goals/{goal_id}/approve", headers=other).status_code == 404
    assert client.get("/initiatives", headers=other).json() == []


def test_quiet_hours_settings_are_validated(client, db, world) -> None:
    headers = _login(client, db)
    ok = client.put(
        "/notifications/settings",
        headers=headers,
        json={"quiet_start": "23:00", "quiet_end": "07:30", "timezone": "America/Sao_Paulo"},
    )
    assert ok.status_code == 200
    bad = client.put(
        "/notifications/settings",
        headers=headers,
        json={"quiet_start": "25:00", "quiet_end": "07:30", "timezone": "Marte/Base"},
    )
    assert bad.status_code == 422


def test_followup_waits_when_the_autonomy_budget_is_spent(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    goal_id = _inconclusive_turn(client, headers)["curiosity"]["proposed_goal_id"]
    client.post(f"/goals/{goal_id}/approve", headers=headers)
    world["search"].results = [CANBERRA]
    llm = FakeLLMProvider()
    spent = {
        "research_followup": research_followup_handler(
            Settings(autonomy_llm_calls_per_day=0), llm, world["search"]
        )
    }

    assert run_once(world["factory"], spent, "w") == "deferred"

    job = db.scalars(select(ScheduledJob)).one()
    db.refresh(job)
    assert job.status == "PENDING" and job.last_error == "autonomy_budget"
    assert client.get("/goals", headers=headers).json()[0]["status"] == "APPROVED"
    assert client.get("/notifications", headers=headers).json() == []
    assert llm.prompts == []
