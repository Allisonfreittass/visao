"""Controlled autonomous cycle (Phase 9 §6): cognition without a new message.

Triggered by schedule (one idempotent job per time window) and by events; never a continuous
loop. Opportunity detection reads the database only (no model call). Execution respects the
global pause, standing permissions and a daily autonomy budget; with a zero budget nothing that
calls a model runs. Every action is persisted as an autonomous decision.
"""

import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.decision.turn import TurnPlan
from core.goals import followup, lifecycle
from core.identity import name_deliberation
from core.identity.genesis import get_identity
from core.initiatives.followup import consider_followup
from core.policies.autonomy import is_paused
from core.reflection.reflect import reflect
from infrastructure.database.models import (
    Conversation,
    Goal,
    IdentityNameEvent,
    KnowledgeGap,
    Message,
    ModelUsage,
    User,
)
from infrastructure.jobs import queue
from integrations.llm.base import LLMProvider
from integrations.search.base import SearchProvider

JOB_KIND = "cognitive_cycle"
AUTONOMOUS_PURPOSES = (
    "name_deliberation",
    "followup_summary",
    "reflection",
    "conversation_followup",
    "study_plan",
    "study_review",
)
REFLECT_AFTER_IDLE = timedelta(minutes=30)
NAME_QUESTION_AFTER = timedelta(days=1)
NAME_QUESTION_EVERY = timedelta(days=30)
MIN_CONVERSATIONS_FOR_NAME = 3


@dataclass(frozen=True)
class AutonomyBudget:
    llm_calls_per_day: int
    tokens_per_day: int
    max_actions_per_cycle: int
    max_seconds: float
    research_per_day: int
    max_output_tokens: int
    daily_usd: Decimal = Decimal("1.50")


@dataclass
class CycleReport:
    skipped: str | None = None
    actions: list[dict] = field(default_factory=list)
    llm_calls_today: int = 0
    tokens_today: int = 0


def _start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def usage_today(session: Session, now: datetime) -> tuple[int, int]:
    row = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(ModelUsage.input_tokens + ModelUsage.output_tokens), 0),
        ).where(
            ModelUsage.purpose.in_(AUTONOMOUS_PURPOSES),
            ModelUsage.created_at >= _start_of_day(now),
        )
    ).one()
    return int(row[0]), int(row[1])


def _budget_left(session: Session, budget: AutonomyBudget, now: datetime) -> bool:
    calls, tokens = usage_today(session, now)
    return calls < budget.llm_calls_per_day and tokens < budget.tokens_per_day


def schedule(session: Session, now: datetime, interval_minutes: int) -> None:
    """Idempotent: one cycle job per window, however often the worker calls this."""
    window = int(now.timestamp() // (interval_minutes * 60))
    queue.enqueue(
        session,
        kind=JOB_KIND,
        payload={"window": window},
        idempotency_key=f"cycle:{interval_minutes}:{window}",
        reason="Ciclo cognitivo agendado",
        run_after=now,
        max_attempts=1,
    )
    session.commit()


def _record(session: Session, owner_id: uuid.UUID | None, **action) -> dict:
    plan = TurnPlan()
    plan.add(
        action.pop("action"), executed=action.pop("executed"), reason=action.pop("reason"), **action
    )
    plan.persist(
        session, owner_id=owner_id, conversation_id=None, message_id=None, origin="autonomous"
    )
    session.commit()
    return plan.actions[0]


def run_cycle(
    session: Session,
    *,
    provider: LLMProvider | None,
    search: SearchProvider,
    budget: AutonomyBudget,
    now: datetime | None = None,
) -> CycleReport:
    now = now or datetime.now(UTC)
    started = time.monotonic()
    report = CycleReport()
    report.llm_calls_today, report.tokens_today = usage_today(session, now)
    if is_paused(session):
        report.skipped = "paused"
        return report
    if provider is None:
        report.skipped = "no_llm"
        return report
    if not _budget_left(session, budget, now):
        report.skipped = "autonomy_budget"
        return report

    def room() -> bool:
        return (
            len(report.actions) < budget.max_actions_per_cycle
            and time.monotonic() - started < budget.max_seconds
            and _budget_left(session, budget, now)
        )

    # 1. Unanswered public-fact questions: propose (free); research if the owner allowed it.
    gaps = session.scalars(
        select(KnowledgeGap)
        .where(
            KnowledgeGap.depends_on == "public_fact",
            KnowledgeGap.status.in_(["DEFERRED", "INCONCLUSIVE"]),
        )
        .order_by(KnowledgeGap.created_at)
    ).all()
    for gap in gaps:
        if not room():
            break
        owner = session.get(User, gap.owner_user_id)
        goal = session.scalar(select(Goal).where(Goal.source_gap_id == gap.id))
        if goal is None:
            query = str(gap.scores.get("search_query") or gap.question)
            goal = followup.propose_followup(session, gap=gap, owner=owner, search_query=query)
            session.commit()
            if goal is not None:
                report.actions.append(
                    _record(
                        session,
                        owner.id,
                        action="goal_proposed",
                        executed=True,
                        reason="unanswered_public_fact",
                        goal_id=str(goal.id),
                    )
                )
        if goal is None or goal.status != lifecycle.EVALUATED:
            continue
        if not (owner.autonomy_permissions or {}).get("auto_research"):
            continue  # waits for the owner's approval in /approvals
        followup.approve_by_standing_permission(session, goal)
        result = followup.run_goal(
            session,
            goal.id,
            provider=provider,
            search=search,
            research_budget_left=followup.research_count_today(session, owner.id)
            < budget.research_per_day,
            max_output_tokens=budget.max_output_tokens,
        )
        report.actions.append(
            _record(
                session,
                owner.id,
                action="research",
                executed=result.outcome == "done",
                reason="standing_permission_auto_research",
                goal_id=str(goal.id),
                **result.detail,
            )
        )

    # Conversational threads need no web permission. Validate once after an idle interval;
    # notifications use the existing quiet hours, daily cap and global pause.
    threads = session.scalars(
        select(KnowledgeGap)
        .where(KnowledgeGap.depends_on == "conversation", KnowledgeGap.status == "DEFERRED")
        .order_by(KnowledgeGap.created_at)
    ).all()
    for gap in threads:
        if not room():
            break
        outcome = consider_followup(
            session,
            gap=gap,
            provider=provider,
            now=now,
            max_output_tokens=budget.max_output_tokens,
        )
        if outcome is not None:
            report.actions.append(
                _record(
                    session,
                    gap.owner_user_id,
                    action="conversation_followup",
                    executed=outcome == "notified",
                    reason=outcome,
                    gap_id=str(gap.id),
                )
            )

    # A study round is one bounded action, with two separately budgeted model calls.
    from core.study.service import study_once

    for owner in session.scalars(select(User).where(User.is_active.is_(True))).all():
        if not room():
            break
        entry = study_once(
            session,
            owner=owner,
            provider=provider,
            search=search,
            now=now,
            budget=replace(
                budget, max_seconds=max(0.001, budget.max_seconds - (time.monotonic() - started))
            ),
        )
        if entry is not None:
            report.actions.append(
                _record(
                    session,
                    owner.id,
                    action="autonomous_study",
                    executed=entry.status == "READY",
                    reason=entry.outcome_reason,
                    study_id=str(entry.id),
                    status=entry.status,
                )
            )

    # 2. Finished conversations not reflected on (reflection only calls the model with evidence).
    idle_since = now - REFLECT_AFTER_IDLE
    candidates = session.scalars(
        select(Conversation).where(Conversation.last_reflected_at.is_(None))
    ).all()
    for conversation in candidates:
        if not room():
            break
        last = session.scalar(
            select(func.max(Message.created_at)).where(Message.conversation_id == conversation.id)
        )
        if last is None or (last if last.tzinfo else last.replace(tzinfo=UTC)) > idle_since:
            continue
        owner = session.get(User, conversation.user_id)
        result = reflect(
            session,
            conversation=conversation,
            owner=owner,
            provider=provider,
            max_output_tokens=budget.max_output_tokens,
        )
        report.actions.append(
            _record(
                session,
                owner.id,
                action="reflection",
                executed=result.skipped_reason is None,
                reason=result.skipped_reason or "finished_conversation",
                conversation_id=str(conversation.id),
                created=result.created,
            )
        )

    # 3. The identity question left open since genesis (only after real use, rarely).
    identity = get_identity(session)
    if identity is not None and identity.chosen_name is None and room():
        created = (
            identity.created_at
            if identity.created_at.tzinfo
            else identity.created_at.replace(tzinfo=UTC)
        )
        last_event = session.scalar(
            select(func.max(IdentityNameEvent.created_at)).where(
                IdentityNameEvent.identity_id == identity.id
            )
        )
        last_event = (
            last_event.replace(tzinfo=UTC) if last_event and not last_event.tzinfo else last_event
        )
        conversations = session.scalar(select(func.count()).select_from(Conversation)) or 0
        owner = session.scalar(select(User).order_by(User.created_at).limit(1))
        if (
            owner is not None
            and conversations >= MIN_CONVERSATIONS_FOR_NAME
            and now - created >= NAME_QUESTION_AFTER
            and (last_event is None or now - last_event >= NAME_QUESTION_EVERY)
        ):
            queued = name_deliberation.request(
                session,
                identity=identity,
                owner=owner,
                reason="questão do nome em aberto desde o genesis",
                now=now,
            )
            session.commit()
            if queued:
                report.actions.append(
                    _record(
                        session,
                        owner.id,
                        action="name_deliberation_requested",
                        executed=True,
                        reason="identity_question_open",
                    )
                )

    report.llm_calls_today, report.tokens_today = usage_today(session, now)
    return report
