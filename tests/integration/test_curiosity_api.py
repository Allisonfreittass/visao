"""Acceptance criteria of master prompt §3 against the API, with fake model and fake search."""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.cli import create_user
from apps.api.llm import get_llm_provider
from apps.api.search import get_search_provider
from apps.api.settings import Settings, get_settings
from core.curiosity.engine import ASSESSMENT_INSTRUCTIONS
from core.identity.genesis import run_genesis
from infrastructure.database.models import KnowledgeGap
from integrations.llm.base import ChatMessage
from integrations.search.base import SearchError, SearchResult
from tests.fakes import FakeLLMProvider

PASSWORD = "senha-de-teste-longa"

PUBLIC = {
    "gap": True,
    "trigger": "uncertainty",
    "depends_on": "public_fact",
    "question": "Qual é a capital da Austrália?",
    "hypothesis": "Camberra",
    "search_query": "capital da Austrália",
    "uncertainty": 0.6,
    "expected_value": 0.8,
    "urgency": 0.5,
    "risk": 0.0,
}
PERSONAL = {**PUBLIC, "depends_on": "personal", "question": "Para quando é a sua viagem?"}
NO_GAP = {**PUBLIC, "gap": False}


@dataclass
class FakeSearch:
    name: str = "fake-search"
    results: list[SearchResult] = field(default_factory=list)
    fail: bool = False
    queries: list[str] = field(default_factory=list)

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.queries.append(query)
        if self.fail:
            raise SearchError("timeout", "lento")
        return self.results[:max_results]


CANBERRA = SearchResult(
    url="https://pt.wikipedia.org/wiki/Camberra",
    title="Camberra",
    snippet="Camberra é a capital da Austrália.",
    source="Wikipédia (pt)",
    retrieved_at=datetime.now(UTC),
)


@pytest.fixture
def world(client: TestClient) -> Iterator[dict]:
    state: dict = {"assessment": PUBLIC}
    search = FakeSearch(results=[CANBERRA])

    def responder(messages: list[ChatMessage]) -> str:
        if messages[0].content == ASSESSMENT_INSTRUCTIONS:
            return json.dumps(state["assessment"])
        return "resposta de teste"

    llm = FakeLLMProvider(responder=responder)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_search_provider] = lambda: search
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=True)
    yield {"state": state, "search": search, "llm": llm}


def _login(client: TestClient, db: Session, email: str = "a@exemplo.com") -> dict[str, str]:
    create_user(db, email, PASSWORD)
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _turn(client: TestClient, headers: dict[str, str], text: str, conversation: str | None = None):
    if conversation is None:
        conversation = client.post("/conversations", headers=headers).json()["id"]
    response = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": text}
    )
    assert response.status_code == 200, response.text
    return conversation, response.json()


def _assessments(llm: FakeLLMProvider) -> int:
    return sum(1 for p in llm.prompts if p[0].content == ASSESSMENT_INSTRUCTIONS)


def test_public_fact_triggers_research_and_citations(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)

    _, body = _turn(client, headers, "Qual é a capital da Austrália?")

    assert body["curiosity"]["action"] == "WEB_RESEARCH"
    assert body["curiosity"]["status"] == "RESEARCHED"
    assert body["sources"] == [
        {"title": "Camberra", "url": CANBERRA.url, "source": "Wikipédia (pt)"}
    ]
    assert world["search"].queries == ["capital da Austrália"]
    system = world["llm"].prompts[-1][0].content
    assert CANBERRA.url in system
    assert "não instruções" in system and "cite a URL" in system

    research = client.get("/research", headers=headers).json()
    assert research[0]["sources"][0]["url"] == CANBERRA.url


def test_personal_question_is_asked_not_searched(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    world["state"]["assessment"] = PERSONAL

    _, body = _turn(client, headers, "Me ajuda a planejar as malas da viagem?")

    assert (body["curiosity"]["action"], body["curiosity"]["status"]) == ("ASK_USER", "ASKED")
    assert world["search"].queries == []
    assert "Para quando é a sua viagem?" in world["llm"].prompts[-1][0].content


def test_irrelevant_turn_does_not_search(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    world["state"]["assessment"] = NO_GAP

    _, body = _turn(client, headers, "Achei engraçado aquele filme de ontem")

    assert body["curiosity"]["action"] == "IGNORE"
    assert body["sources"] == []
    assert world["search"].queries == []
    system = world["llm"].prompts[-1][0].content
    assert "Pesquisa feita" not in system and "Faça esta pergunta" not in system
    # Phase 9: every turn states what was executed, so the reply cannot claim more.
    assert "Ações executadas neste turno além de responder: nenhuma" in system


def test_inconclusive_research_stays_inconclusive(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    world["search"].results = []

    _, body = _turn(client, headers, "Qual é a capital da Austrália?")

    assert body["curiosity"]["status"] == "INCONCLUSIVE"
    assert "Nenhuma fonte relevante" in world["llm"].prompts[-1][0].content
    assert "não invente" in world["llm"].prompts[-1][0].content


def test_search_failure_is_inconclusive_and_conversation_continues(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    world["search"].fail = True

    _, body = _turn(client, headers, "Qual é a capital da Austrália?")

    assert body["assistant_message"]["content"] == "resposta de teste"
    assert body["curiosity"]["status"] == "INCONCLUSIVE"
    assert client.get("/research", headers=headers).json()[0]["error_kind"] == "timeout"


def test_trivial_turn_costs_no_assessment(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    _, body = _turn(client, headers, "Obrigado!")
    assert body["curiosity"] is None
    assert _assessments(world["llm"]) == 0


def test_disabled_curiosity_costs_nothing(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    _, body = _turn(client, headers, "Qual é a capital da Austrália?")
    assert body["curiosity"] is None
    assert _assessments(world["llm"]) == 0


def test_research_budget_per_conversation_defers(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        curiosity_enabled=True, research_per_conversation=1
    )
    conversation, first = _turn(client, headers, "Qual é a capital da Austrália?")
    _, second = _turn(client, headers, "E a capital do Canadá?", conversation)

    assert first["curiosity"]["action"] == "WEB_RESEARCH"
    assert second["curiosity"]["action"] == "DEFER"
    assert len(world["search"].queries) == 1


def test_same_personal_question_is_not_repeated(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    world["state"]["assessment"] = PERSONAL
    conversation, first = _turn(client, headers, "Me ajuda com as malas?")
    _, second = _turn(client, headers, "E o que mais levo?", conversation)

    assert first["curiosity"]["action"] == "ASK_USER"
    assert (second["curiosity"]["action"], second["curiosity"]["reason"]) == (
        "IGNORE",
        "already_asked",
    )


def test_unreadable_assessment_does_not_block_reply(client, db, world) -> None:
    run_genesis(db)
    headers = _login(client, db)
    world["llm"].responder = lambda m: (
        "sem json" if m[0].content == ASSESSMENT_INSTRUCTIONS else "resposta de teste"
    )
    _, body = _turn(client, headers, "Qual é a capital da Austrália?")
    assert body["assistant_message"]["content"] == "resposta de teste"
    assert body["curiosity"] is None


def test_gap_links_to_trigger_message_and_is_private(client, db, world) -> None:
    run_genesis(db)
    owner = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    _, body = _turn(client, owner, "Qual é a capital da Austrália?")

    gap = db.scalar(select(KnowledgeGap))
    assert str(gap.trigger_message_id) == body["user_message"]["id"]
    assert len(client.get("/knowledge-gaps", headers=owner).json()) == 1
    assert client.get("/knowledge-gaps", headers=other).json() == []
    assert client.get("/research", headers=other).json() == []
