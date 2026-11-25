"""Job kind -> handler wiring for the worker process."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from apps.api.browser import get_browser
from apps.api.limits import panel_limits
from apps.api.llm import build_llm_provider, with_brain
from apps.api.settings import Settings
from apps.worker.runner import Handler, HandlerResult
from core.autonomy.budget import has_room
from core.autonomy.cycle import AutonomyBudget, run_cycle, usage_today
from core.autonomy.cycle import _record as record_action
from core.conversation import segments
from core.conversation import title as conversation_title
from core.conversation.service import Budgets
from core.goals.followup import research_count_today, run_followup
from core.identity import name_deliberation
from core.identity.genesis import get_identity
from core.mind import briefing
from core.mind.review import review_once
from core.mind.think import MindConfig, think_once
from core.panels import service as panels
from infrastructure.database.models import Goal, Panel, ScheduledJob, User
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
        # The summary is an autonomous model call: it shares the agent's own daily budget.
        if goal is not None and not autonomy_room(session, settings):
            return HandlerResult("defer", defer_until=_tomorrow(), reason="autonomy_budget")
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


def _tomorrow() -> datetime:
    return (datetime.now(UTC) + timedelta(days=1)).replace(hour=9, minute=0, second=0)


def autonomy_room(session: Session, settings: Settings, calls: int = 1) -> bool:
    """``calls`` more autonomous model calls fit today's autonomy and USD budgets."""
    return has_room(session, autonomy_budget(settings), datetime.now(UTC), calls)


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
            google_secret=settings.secret_key,
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


def think_handler(settings: Settings, provider: LLMProvider | None) -> Handler:
    """A thinking round at a time the agent chose (core.mind.intentions), outside the cycle."""

    def handle(session: Session, job: ScheduledJob) -> HandlerResult:
        owner = session.get(User, uuid.UUID(job.payload["owner_id"]))
        budget = autonomy_budget(settings)
        if provider is None or owner is None or budget.mind is None:
            return HandlerResult("done", {"skipped": "mind_off"})
        result = think_once(
            session, owner=owner, provider=provider, budget=budget, config=budget.mind
        )
        if result.reason != "not_due":
            record_action(
                session,
                owner.id,
                action="mind_think",
                executed=result.thought is not None,
                reason=result.reason,
                delivery=result.delivery,
                trigger=job.reason,
            )
        return HandlerResult("done", {"reason": result.reason, "delivery": result.delivery})

    return handle


def title_handler(settings: Settings, provider: LLMProvider | None) -> Handler:
    """A conversation's title for the menu (core/conversation/title.py). Answering the owner's
    own conversation, so it counts against the chat budget, not the autonomy one."""

    def handle(session: Session, job: ScheduledJob) -> HandlerResult:
        if provider is None:
            return HandlerResult("done", {"skipped": "no_llm"})
        budgets = Budgets(settings.llm_daily_budget_usd, settings.llm_conversation_budget_usd)
        named = conversation_title.run_job(
            session,
            uuid.UUID(job.payload["conversation_id"]),
            provider,
            budgets,
            again=bool(job.payload.get("retitle")),
        )
        return HandlerResult("done", {"titled": named is not None})

    return handle


def segment_handler(settings: Settings, provider: LLMProvider | None) -> Handler:
    """Closes and summarizes the continuous conversation's segments (ADR-0014): the agent's own
    call, so it counts in the autonomy budget. Without room, a segment stays read raw."""

    def handle(session: Session, job: ScheduledJob) -> HandlerResult:
        closed = segments.run_job(
            session,
            uuid.UUID(job.payload["conversation_id"]),
            provider,
            has_room=lambda: autonomy_room(session, settings),
        )
        return HandlerResult("done", {"closed": closed})

    return handle


def panel_handler(settings: Settings, provider: LLMProvider | None) -> Handler:
    """The check of a live panel (core/panels/service.py, ADR-0012 and 0016): the agent's own
    call, so it counts in the autonomy budget and stops with the global pause. A job for a check
    that was moved since (edit, pause, closer to the goal) does nothing."""

    def handle(session: Session, job: ScheduledJob) -> HandlerResult:
        panel = session.get(Panel, uuid.UUID(job.payload["panel_id"]))
        if panel is None:
            return HandlerResult("done", {"skipped": "deleted"})
        owner = session.get(User, panel.owner_user_id)
        if owner is None:
            return HandlerResult("done", {"skipped": "no_owner"})
        if panels.stale(panel, job.payload.get("at")):
            return HandlerResult("done", {"skipped": "moved"})
        outcome = panels.recheck(
            session,
            panel,
            owner=owner,
            browser=get_browser(),
            provider=provider,
            limits=panel_limits(settings),
            has_room=lambda: autonomy_room(session, settings),
        )
        return HandlerResult("done", {"outcome": outcome})

    return handle


def briefing_handler(settings: Settings, provider: LLMProvider | None) -> Handler:
    """The morning briefing (core/mind/briefing.py, ADR-0017): the agent's own call, in the
    autonomy budget; it checks the live panels first, in place of their 9h check."""

    def handle(session: Session, job: ScheduledJob) -> HandlerResult:
        owner = session.get(User, uuid.UUID(job.payload["owner_id"]))
        if owner is None:
            return HandlerResult("done", {"skipped": "no_owner"})
        report = briefing.run(
            session,
            owner,
            provider=provider,
            budget=autonomy_budget(settings),
            google_secret=settings.secret_key,
            browser=get_browser(),
            limits=panel_limits(settings),
            has_room=lambda: autonomy_room(session, settings),
            asked=bool(job.payload.get("asked")),
            backup_dir=settings.backup_status_dir,
        )
        record_action(
            session,
            owner.id,
            action="morning_briefing",
            executed=report.sent,
            reason=report.reason,
            items=report.items,
            written_by=report.written_by,
        )
        return HandlerResult("done", {"reason": report.reason, "items": report.items})

    return handle


def build_handlers(settings: Settings) -> dict[str, Handler]:
    # Work done on its own: paused while the owner runs on the local model (core/brain.py).
    provider = with_brain(settings, build_llm_provider(settings), background=True)
    # With reasoning on, a long conversation filled the output limit and the JSON came back cut.
    fast = with_brain(settings, build_llm_provider(settings, fast=True), background=True)
    search = OpenWebSearch() if settings.mind_enabled else WikipediaSearch()
    return {
        "research_followup": research_followup_handler(settings, provider, search),
        "cognitive_cycle": cycle_handler(settings, provider, search, fast),
        "name_deliberation": name_handler(settings, provider),
        "mind_review": review_handler(settings, fast),
        "mind_think": think_handler(settings, provider),
        conversation_title.JOB_KIND: title_handler(settings, fast),
        panels.JOB_KIND: panel_handler(settings, fast),
        segments.JOB_KIND: segment_handler(settings, fast),
        briefing.JOB_KIND: briefing_handler(settings, fast),
    }
