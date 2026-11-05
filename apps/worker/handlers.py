"""Job kind -> handler wiring for the worker process."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from apps.api.llm import build_llm_provider
from apps.api.settings import Settings
from apps.worker.runner import Handler, HandlerResult
from core.autonomy.cycle import AutonomyBudget, run_cycle, usage_today
from core.goals.followup import research_count_today, run_followup
from core.identity import name_deliberation
from core.identity.genesis import get_identity
from core.mind.review import review_once
from core.mind.think import MindConfig
from infrastructure.database.models import Goal, ScheduledJob, User
from integrations.llm.base import LLMProvider
from integrations.search.base import SearchProvider
from integrations.search.open_web import OpenWebSearch
from integrations.search.wikipedia import WikipediaSearch


def research_followup_handler(
    settings: Settings, provider: LLMProvider | None, search: SearchProvider
) -> Handler:
    def handle(session: Session, job: ScheduledJob) -> HandlerResult:
        if provider is None:
            raise RuntimeError("LLM not configured")
        goal = session.get(Goal, uuid.UUID(job.payload["goal_id"]))
        owner_id = goal.owner_user_id if goal else None
        budget_left = owner_id is None or (
            research_count_today(session, owner_id) < settings.research_per_day
        )
        result = run_followup(
            session,
            job,
            provider=provider,
            search=search,
            research_budget_left=budget_left,
            max_output_tokens=settings.llm_curation_max_output_tokens,
        )
        return HandlerResult(
            outcome="defer" if result.outcome == "defer" else "done",
            result=result.detail,
            defer_until=result.defer_until,
            reason=str(result.detail.get("reason", "")),
        )

    return handle


def autonomy_budget(
    settings: Settings, review_provider: LLMProvider | None = None
) -> AutonomyBudget:
    return AutonomyBudget(
        llm_calls_per_day=settings.autonomy_llm_calls_per_day,
        tokens_per_day=settings.autonomy_tokens_per_day,
        max_actions_per_cycle=settings.autonomy_max_actions_per_cycle,
        max_seconds=settings.autonomy_max_seconds,
        research_per_day=settings.research_per_day,
        max_output_tokens=settings.llm_curation_max_output_tokens,
        daily_usd=settings.llm_daily_budget_usd,
        study_interval=timedelta(minutes=settings.study_interval_minutes),
        open_web=settings.mind_enabled,
        mind=MindConfig(
            think_every=timedelta(minutes=settings.mind_think_minutes),
            initiatives_per_day=settings.mind_initiatives_per_day,
            review_provider=review_provider,
        )
        if settings.mind_enabled
        else None,
    )


def cycle_handler(
    settings: Settings,
    provider: LLMProvider | None,
    search: SearchProvider,
    review_provider: LLMProvider | None = None,
) -> Handler:
    def handle(session: Session, job: ScheduledJob) -> HandlerResult:
        report = run_cycle(
            session,
            provider=provider,
            search=search,
            budget=autonomy_budget(settings, review_provider),
        )
        return HandlerResult(
            "done",
            {
                "skipped": report.skipped,
                "actions": report.actions,
                "llm_calls_today": report.llm_calls_today,
            },
        )

    return handle


def review_handler(settings: Settings, provider: LLMProvider | None) -> Handler:
    def handle(session: Session, job: ScheduledJob) -> HandlerResult:
        owner = session.get(User, uuid.UUID(job.payload["owner_id"]))
        if provider is None or owner is None:
            raise RuntimeError("LLM or owner missing")
        report = review_once(
            session, owner=owner, provider=provider, budget=autonomy_budget(settings)
        )
        return HandlerResult(
            "done",
            {
                "outcome": report.outcome,
                "changed": list(report.changed),
                "rejected": list(report.rejected),
            },
        )

    return handle


def name_handler(settings: Settings, provider: LLMProvider | None) -> Handler:
    def handle(session: Session, job: ScheduledJob) -> HandlerResult:
        identity = get_identity(session)
        if provider is None or identity is None:
            raise RuntimeError("LLM or identity missing")
        calls, tokens = usage_today(session, datetime.now(UTC))
        if (
            calls >= settings.autonomy_llm_calls_per_day
            or tokens >= settings.autonomy_tokens_per_day
        ):
            tomorrow = (datetime.now(UTC) + timedelta(days=1)).replace(hour=9, minute=0)
            return HandlerResult("defer", defer_until=tomorrow, reason="autonomy_budget")
        result = name_deliberation.run_job(
            session,
            job.payload,
            provider=provider,
            identity=identity,
            max_output_tokens=settings.llm_curation_max_output_tokens,
        )
        return HandlerResult("done", result)

    return handle


def build_handlers(settings: Settings) -> dict[str, Handler]:
    provider = build_llm_provider(settings)
    # With reasoning on, a long conversation filled the output limit and the JSON came back cut.
    fast = build_llm_provider(settings, fast=True)
    search = OpenWebSearch() if settings.mind_enabled else WikipediaSearch()
    return {
        "research_followup": research_followup_handler(settings, provider, search),
        "cognitive_cycle": cycle_handler(settings, provider, search, fast),
        "name_deliberation": name_handler(settings, provider),
        "mind_review": review_handler(settings, fast),
    }
