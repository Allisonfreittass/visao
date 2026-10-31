"""Autonomous study: real persistence and worker cycle, deterministic provider/search doubles."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from apps.api.cli import create_user
from core.autonomy.cycle import run_cycle, usage_today
from core.identity.genesis import run_genesis
from core.policies.autonomy import set_paused
from core.research.budget import searches_today
from core.study.service import PLAN_INSTRUCTIONS, related_context, study_once
from infrastructure.database.models import (
    MemoryCandidate,
    MemoryRecord,
    Notification,
    ScheduledJob,
    User,
)
from integrations.search.base import SearchError, SearchResult
from tests.fakes import FakeLLMProvider
from tests.integration.test_phase9 import _budget, _world

PLAN = {
    "study": True,
    "public_topic": True,
    "sensitive": False,
    "private_person": False,
    "topic": "Organização do conhecimento",
    "question": "O que é classificação facetada?",
    "query": "classificação facetada",
    "rationale": "Comparar formas de organizar informação.",
    "seed_refs": [],
}
REVIEW = {
    "findings": [
        {"claim": "Classificação facetada organiza por múltiplas características.", "sources": [1]}
    ],
    "uncertain": "Os trechos não permitem avaliar aplicação na oficina fictícia.",
    "next_question": "Como funciona uma taxonomia?",
    "next_query": "taxonomia",
    "public_topic": True,
    "sensitive": False,
    "private_person": False,
    "worth_sharing": False,
}


class Search:
    name = "wikipedia-test"
    calls = 0
    fail = False

    def search(self, query, max_results):
        self.calls += 1
        if self.fail:
            raise SearchError("network", "simulated")
        return [
            SearchResult(
                url="https://pt.wikipedia.org/wiki/Classifica%C3%A7%C3%A3o_facetada",
                title="Classificação facetada",
                snippet="Classificação facetada organiza por múltiplas características.",
                source="Wikipédia",
                retrieved_at=datetime.now(UTC),
            )
        ]


def world(db, plan=None, review=None):
    _, owner = _world(db)
    owner.autonomy_permissions = {"auto_study": True}
    db.commit()

    def respond(messages):
        return json.dumps(
            (plan if plan is not None else PLAN)
            if messages[0].content.startswith(PLAN_INSTRUCTIONS)
            else (review if review is not None else REVIEW)
        )

    return owner, FakeLLMProvider(responder=respond), Search()


def run(db, owner, llm, search, budget=None, now=None):
    return study_once(
        db,
        owner=owner,
        provider=llm,
        search=search,
        budget=budget or _budget(),
        now=now or datetime.now(UTC),
    )


def test_study_records_provenance_uncertainty_and_daily_usage(db):
    owner, llm, search = world(db)
    entry = run(db, owner, llm, search)
    assert entry.status == "READY"
    assert len(llm.prompts) == 2 and search.calls == 1
    assert entry.evidence["findings"][0]["sources"] == [1]
    assert entry.evidence["sources"][0]["url"].startswith("https://pt.wikipedia.org/wiki/")
    assert entry.evidence["uncertain"] and entry.evidence["next_question"]
    assert usage_today(db, datetime.now(UTC)) == (2, 3000)
    assert searches_today(db, owner.id) == 1
    assert db.scalar(select(MemoryRecord)) is None  # research is not automatic personal memory
    assert db.scalar(select(Notification)) is None  # no notification just because a cycle ran
    assert run(db, owner, llm, search) is None
    assert len(llm.prompts) == 2


@pytest.mark.parametrize("block", ["disabled", "paused", "calls", "tokens", "dollars", "searches"])
def test_study_respects_permission_and_all_budgets_before_calls(db, block):
    owner, llm, search = world(db)
    budget = _budget()
    if block == "disabled":
        owner.autonomy_permissions = {}
        db.commit()
    elif block == "paused":
        set_paused(db, True, actor_user_id=owner.id, reason="teste")
    elif block == "calls":
        budget = replace(budget, llm_calls_per_day=1)
    elif block == "tokens":
        budget = replace(budget, tokens_per_day=0)
    elif block == "dollars":
        budget = replace(budget, daily_usd=Decimal("0"))
    else:
        budget = replace(budget, research_per_day=0)
    assert run(db, owner, llm, search, budget) is None
    assert not llm.prompts and search.calls == 0


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"study": False}, "no_useful_question"),
        ({"sensitive": True}, "not_public_topic"),
        ({"private_person": True}, "not_public_topic"),
        ({"query": "senha de teste"}, "not_public_topic"),
        ({"query": "https://example.com"}, "not_public_topic"),
        ({"seed_refs": ["memory:invented"]}, "invalid_seed_reference"),
    ],
)
def test_invalid_or_private_topics_never_reach_search(db, change, reason):
    owner, llm, search = world(db, plan={**PLAN, **change})
    entry = run(db, owner, llm, search)
    assert entry.status == "SKIPPED" and entry.outcome_reason == reason
    assert search.calls == 0


def test_unknown_citation_ids_cannot_become_findings(db):
    owner, llm, search = world(
        db,
        review={
            **REVIEW,
            "findings": [
                {"claim": "Unsupported", "sources": [99]},
                {"claim": "Bool is not id", "sources": [True]},
            ],
        },
    )
    entry = run(db, owner, llm, search)
    assert entry.status == "INCONCLUSIVE"
    assert not entry.evidence["findings"]


@pytest.mark.parametrize("failure", ["llm", "search", "json"])
def test_failures_are_visible_and_do_not_spin_or_notify(db, failure):
    owner, llm, search = world(db)
    if failure == "llm":
        llm.fail_with = "timeout"
    elif failure == "search":
        search.fail = True
    else:
        llm.responder = lambda messages: "not JSON"
    entry = run(db, owner, llm, search)
    assert entry.status == "FAILED" and entry.finished_at is not None
    assert run(db, owner, llm, search) is None
    assert db.scalar(select(Notification)) is None


def test_revoking_permission_during_planning_prevents_search(db):
    owner, llm, search = world(db)

    def respond(messages):
        owner.autonomy_permissions = {}
        db.commit()
        return json.dumps(PLAN)

    llm.responder = respond
    entry = run(db, owner, llm, search)
    assert entry.outcome_reason == "permission_revoked"
    assert search.calls == 0


def test_study_continues_notebook_and_rejects_repeated_question(db):
    owner, llm, search = world(db)
    now = datetime.now(UTC)
    first = run(db, owner, llm, search, now=now)
    first.created_at = now - timedelta(hours=7)
    db.commit()
    repeated = run(db, owner, llm, search, now=now)
    assert repeated is None  # same six-hour window claim remains reserved
    # Use the next actual window; previous entry is old enough for another round.
    future = now + timedelta(hours=7)
    second = run(db, owner, llm, search, now=future)
    assert second.outcome_reason == "repeated_question"
    seeds = json.loads(llm.prompts[-1][1].content)["seeds"]
    assert seeds[0]["next_question"] == REVIEW["next_question"]


def test_round_can_select_previous_question_with_valid_provenance(db):
    owner, llm, search = world(db)
    first = run(db, owner, llm, search)
    future = datetime.now(UTC) + timedelta(hours=7)
    new_plan = {
        **PLAN,
        "question": REVIEW["next_question"],
        "query": REVIEW["next_query"],
        "seed_refs": [f"study:{first.id}"],
    }
    llm.responder = lambda messages: json.dumps(
        new_plan if messages[0].content.startswith(PLAN_INSTRUCTIONS) else REVIEW
    )
    second = run(db, owner, llm, search, now=future)
    assert second.previous_entry_id == first.id and second.status == "READY"


def test_personal_memory_is_not_used_as_seed_without_consent(db):
    owner, llm, search = world(db)
    owner.memory_consent = False
    candidate = MemoryCandidate(
        owner_user_id=owner.id,
        memory_type="relational",
        content="Gosta de um projeto pessoal.",
        evidence_message_ids=[],
        proposed_decision="store",
        scores={},
        flags={},
        rationale="teste",
    )
    db.add(candidate)
    db.flush()
    db.add(
        MemoryRecord(
            owner_user_id=owner.id,
            candidate_id=candidate.id,
            memory_type="relational",
            content=candidate.content,
            confidence=0.9,
        )
    )
    db.commit()
    run(db, owner, llm, search)
    assert json.loads(llm.prompts[0][1].content)["seeds"] == []


def test_notebook_recall_is_scoped_to_owner_and_includes_sources(db):
    owner, llm, search = world(db)
    run(db, owner, llm, search)
    other = User(email="other@exemplo.com", password_hash="!")
    db.add(other)
    db.commit()
    assert related_context(db, other.id, "O que você estudou?") is None
    context = related_context(db, owner.id, "O que você estudou?")
    assert "Classifica" in context and "wikipedia.org" in context


def test_scheduled_cycle_executes_an_enabled_study(db):
    owner, llm, search = world(db)
    report = run_cycle(db, provider=llm, search=search, budget=_budget())
    assert any(a["action"] == "autonomous_study" and a["executed"] for a in report.actions)


def login(client, db, email):
    create_user(db, email, "senha-de-teste-longa")
    token = client.post(
        "/auth/login", data={"username": email, "password": "senha-de-teste-longa"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_notebook_api_is_private_off_by_default_and_queues_on_opt_in(client, db):
    run_genesis(db)
    headers = login(client, db, "api@exemplo.com")
    assert client.get("/study").status_code == 401
    assert client.get("/study", headers=headers).json()["enabled"] is False
    assert client.put("/study/settings", headers=headers, json={"enabled": True}).json() == {
        "enabled": True
    }
    job = db.scalar(select(ScheduledJob))
    assert job.kind == "cognitive_cycle" and "study_owner" in job.payload
    client.put("/study/settings", headers=headers, json={"enabled": True})
    assert len(db.scalars(select(ScheduledJob)).all()) == 1
    assert client.put("/study/settings", headers=headers, json={"enabled": False}).json() == {
        "enabled": False
    }


def test_empty_search_tries_short_topic_once_and_counts_both_attempts(db):
    owner, llm, search = world(db)
    original = search.search
    calls = []

    def lookup(query, max_results):
        calls.append(query)
        return [] if len(calls) == 1 else original(query, max_results)

    search.search = lookup
    entry = run(db, owner, llm, search)
    assert calls == [PLAN["query"], PLAN["topic"]]
    assert entry.status == "READY"
    assert searches_today(db, owner.id) == 2


def test_query_fallback_cannot_exceed_daily_search_quota(db):
    owner, llm, search = world(db)
    queries = []

    def lookup(query, max_results):
        queries.append(query)
        return []

    search.search = lookup
    entry = run(db, owner, llm, search, budget=replace(_budget(), research_per_day=1))
    assert len(queries) == 1
    assert entry.status == "INCONCLUSIVE"
    assert searches_today(db, owner.id) == 1


def test_inconclusive_notebook_is_recalled_as_inconclusive_not_as_a_finding(db):
    owner, llm, search = world(db)
    search.search = lambda query, max_results: []
    entry = run(db, owner, llm, search)
    assert entry.status == "INCONCLUSIVE"
    context = related_context(db, owner.id, "O que está investigando agora?")
    assert '"status": "INCONCLUSIVE"' in context
    assert '"findings": []' in context
    assert '"sources": []' in context


def inconclusive_round(db, owner, llm, search):
    original = search.search
    search.search = lambda query, max_results: []
    first = run(db, owner, llm, search)
    first.created_at = first.created_at.replace(hour=12, minute=0, second=0, microsecond=0)
    first.finished_at = first.created_at + timedelta(seconds=30)
    db.commit()
    search.search = original
    return first, first.finished_at + timedelta(hours=1)


def retry_plan(llm, **changes):
    plan = {**PLAN, "query": "biblioteconomia", "topic": "Ciência da informação", **changes}
    llm.responder = lambda messages: json.dumps(
        plan if messages[0].content.startswith(PLAN_INSTRUCTIONS) else REVIEW
    )


def test_inconclusive_retry_waits_an_hour_then_preserves_question_and_provenance(db):
    owner, llm, search = world(db)
    first, due = inconclusive_round(db, owner, llm, search)
    retry_plan(llm, question="Esta pergunta do planejador não deve substituir a original")
    calls = len(llm.prompts)
    assert run(db, owner, llm, search, now=due - timedelta(seconds=1)) is None
    assert len(llm.prompts) == calls
    second = run(db, owner, llm, search, now=due)
    assert second.status == "READY"
    assert second.question == first.question
    assert second.previous_entry_id == first.id
    assert f"study:{first.id}" in second.seed_refs
    payload = json.loads(llm.prompts[-2][1].content)
    assert payload["retry"]["previous_queries"] == first.evidence["search_queries"]
    assert payload["retry"]["question"] == first.question
    assert first.status == "INCONCLUSIVE"  # preserve the unsuccessful attempt
    assert searches_today(db, owner.id) == 3  # both original lookups plus the retry
    assert run(db, owner, llm, search, now=due + timedelta(hours=1)) is None


def test_second_inconclusive_attempt_cannot_create_an_hourly_retry_loop(db):
    owner, llm, search = world(db)
    first, due = inconclusive_round(db, owner, llm, search)
    retry_plan(llm)
    search.search = lambda query, max_results: []
    second = run(db, owner, llm, search, now=due)
    assert second.status == "INCONCLUSIVE"
    calls = len(llm.prompts)
    assert run(db, owner, llm, search, now=due + timedelta(hours=1)) is None
    assert len(llm.prompts) == calls
    # A stale worker that saw only the original round still cannot claim another retry.
    from sqlalchemy import update

    from infrastructure.database.models import StudyEntry

    db.execute(
        update(StudyEntry)
        .where(StudyEntry.id == second.id)
        .values(created_at=first.created_at - timedelta(seconds=1))
    )
    db.commit()
    assert run(db, owner, llm, search, now=due + timedelta(hours=2)) is None
    assert len(llm.prompts) == calls


def test_retry_never_repeats_the_failed_queries(db):
    owner, llm, search = world(db)
    first, due = inconclusive_round(db, owner, llm, search)
    calls = search.calls
    second = run(db, owner, llm, search, now=due)
    assert second.status == "SKIPPED" and second.outcome_reason == "repeated_query"
    assert search.calls == calls
    assert second.previous_entry_id == first.id


@pytest.mark.parametrize("block", ["disabled", "paused", "calls", "tokens", "dollars", "searches"])
def test_retry_respects_existing_permission_and_budget_limits(db, block):
    owner, llm, search = world(db)
    _, due = inconclusive_round(db, owner, llm, search)
    budget = _budget()
    if block == "disabled":
        owner.autonomy_permissions = {}
        db.commit()
    elif block == "paused":
        set_paused(db, True, actor_user_id=owner.id, reason="teste")
    elif block == "calls":
        budget = replace(budget, llm_calls_per_day=2)
    elif block == "tokens":
        budget = replace(budget, tokens_per_day=0)
    elif block == "dollars":
        budget = replace(budget, daily_usd=Decimal("0"))
    else:
        budget = replace(budget, research_per_day=2)
    calls = len(llm.prompts)
    assert run(db, owner, llm, search, budget, now=due) is None
    assert len(llm.prompts) == calls


def test_notebook_api_and_context_show_retry_time_and_history(client, db):
    owner, llm, search = world(db)
    first, due = inconclusive_round(db, owner, llm, search)
    from apps.api.security import create_access_token
    from apps.api.settings import get_settings

    headers = {"Authorization": "Bearer " + create_access_token(owner.id, get_settings())}
    body = client.get("/study", headers=headers).json()
    assert datetime.fromisoformat(body["next_eligible_at"].replace("Z", "+00:00")) == due
    context = related_context(db, owner.id, "Aprendeu algo?")
    state = json.loads(context.split("\n", 1)[1])
    assert state["entries"][0]["status"] == "INCONCLUSIVE"
    assert state["entries"][0]["created_at"]
    assert state["entries"][0]["finished_at"]
    assert datetime.fromisoformat(state["next_eligible_at"]) == due
    assert state["enabled"] and not state["paused"]


def test_failed_attempt_is_visible_in_history_without_early_retry(db):
    owner, llm, search = world(db)
    llm.fail_with = "timeout"
    first = run(db, owner, llm, search)
    assert first.status == "FAILED"
    context = related_context(db, owner.id, "Você pesquisou algo?")
    assert '"status": "FAILED"' in context
    assert run(db, owner, llm, search, now=first.created_at + timedelta(hours=1)) is None
