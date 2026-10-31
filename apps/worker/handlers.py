"""Job kind -> handler wiring for the worker process."""

import uuid

from sqlalchemy.orm import Session

from apps.api.llm import build_llm_provider
from apps.api.settings import Settings
from apps.worker.runner import Handler, HandlerResult
from core.goals.followup import research_count_today, run_followup
from infrastructure.database.models import Goal, ScheduledJob
from integrations.llm.base import LLMProvider
from integrations.search.base import SearchProvider
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


def build_handlers(settings: Settings) -> dict[str, Handler]:
    return {
        "research_followup": research_followup_handler(
            settings, build_llm_provider(settings), WikipediaSearch()
        )
    }
