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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.autonomy.budget import (
    AUTONOMOUS_PURPOSES as AUTONOMOUS_PURPOSES,  # re-exported: callers read it from here
)
from core.autonomy.budget import AutonomyBudget, budget_left, usage_today
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
    User,
)
from infrastructure.jobs import queue
from integrations.llm.base import LLMProvider
from integrations.search.base import SearchProvider

JOB_KIND = "cognitive_cycle"
REFLECT_AFTER_IDLE = timedelta(minutes=30)
NAME_QUESTION_AFTER = timedelta(days=1)
NAME_QUESTION_EVERY = timedelta(days=30)
MIN_CONVERSATIONS_FOR_NAME = 3


@dataclass
class CycleReport:
    skipped: str | None = None
    actions: list[dict] = field(default_factory=list)
    llm_calls_today: int = 0
    tokens_today: int = 0


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
    report.skipped = _skip_reason(session, provider, budget, now)
    if report.skipped:
        return report
    cycle = _Cycle(session, provider, search, budget, now, started, report)
    # Thinking comes first: it can shape what gets studied and said in this same cycle.
    _think_and_review(cycle)
    _follow_up_public_facts(cycle)
    _follow_up_conversation_threads(cycle)
    _study(cycle)
    _reflect_on_finished_conversations(cycle)
    _consider_the_name_question(cycle)
    report.llm_calls_today, report.tokens_today = usage_today(session, now)
    return report


def _skip_reason(
    session: Session, provider: LLMProvider | None, budget: AutonomyBudget, now: datetime
) -> str | None:
    if is_paused(session):
        return "paused"
    if provider is None:
        return "no_llm"
    if not budget_left(session, budget, now):
        return "autonomy_budget"
    return None


@dataclass
class _Cycle:
    """One running cycle: what every step needs, and the room it shares with the others."""

    session: Session
    provider: LLMProvider
    search: SearchProvider
    budget: AutonomyBudget
    now: datetime
    started: float  # time.monotonic() when the cycle began
    report: CycleReport

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def room(self) -> bool:
        return (
            len(self.report.actions) < self.budget.max_actions_per_cycle
            and self.elapsed() < self.budget.max_seconds
            and budget_left(self.session, self.budget, self.now)
        )

    def record(self, owner_id: uuid.UUID | None, **action) -> None:
        self.report.actions.append(_record(self.session, owner_id, **action))

    def active_owners(self) -> list[User]:
        return list(self.session.scalars(select(User).where(User.is_active.is_(True))).all())


def _think_and_review(cycle: _Cycle) -> None:
    """Per owner: an idle conversation review when one is due, then a round of thinking."""
    mind = cycle.budget.mind
    if mind is None:
        return
    from core.mind.review import idle_review_due, review_once
    from core.mind.think import think_once

    session, now = cycle.session, cycle.now
    for owner in cycle.active_owners():
        if cycle.room() and idle_review_due(session, owner, now):
            reviewed = review_once(
                session,
                owner=owner,
                provider=mind.review_provider or cycle.provider,
                budget=cycle.budget,
                now=now,
            )
            cycle.record(
                owner.id,
                action="mind_review",
                executed=reviewed.outcome == "reviewed",
                reason=reviewed.outcome,
                changed=list(reviewed.changed),
                rejected=list(reviewed.rejected),
            )
        if not cycle.room():
            break
        result = think_once(
            session, owner=owner, provider=cycle.provider, budget=cycle.budget, config=mind, now=now
        )
        if result.reason != "not_due":
            cycle.record(
                owner.id,
                action="mind_think",
                executed=result.thought is not None,
                reason=result.reason,
                delivery=result.delivery,
            )


def _follow_up_public_facts(cycle: _Cycle) -> None:
    """Unanswered public-fact questions: propose (free); research if the owner allowed it."""
    session = cycle.session
    gaps = session.scalars(
        select(KnowledgeGap)
        .where(
            KnowledgeGap.depends_on == "public_fact",
            KnowledgeGap.status.in_(["DEFERRED", "INCONCLUSIVE"]),
        )
        .order_by(KnowledgeGap.created_at)
    ).all()
    for gap in gaps:
        if not cycle.room():
            break
        owner = session.get(User, gap.owner_user_id)
        goal = session.scalar(select(Goal).where(Goal.source_gap_id == gap.id))
        if goal is None:
            goal = _propose_goal(cycle, gap, owner)
        if goal is None or goal.status != lifecycle.EVALUATED:
            continue
        if not (owner.autonomy_permissions or {}).get("auto_research"):
            continue  # waits for the owner's approval in /approvals
        _research_with_standing_permission(cycle, goal, owner)


def _propose_goal(cycle: _Cycle, gap: KnowledgeGap, owner: User) -> Goal | None:
    query = str(gap.scores.get("search_query") or gap.question)
    goal = followup.propose_followup(cycle.session, gap=gap, owner=owner, search_query=query)
    cycle.session.commit()
    if goal is not None:
        cycle.record(
            owner.id,
            action="goal_proposed",
            executed=True,
            reason="unanswered_public_fact",
            goal_id=str(goal.id),
        )
    return goal


def _research_with_standing_permission(cycle: _Cycle, goal: Goal, owner: User) -> None:
    session, budget = cycle.session, cycle.budget
    followup.approve_by_standing_permission(session, goal)
    result = followup.run_goal(
        session,
        goal.id,
        provider=cycle.provider,
        search=cycle.search,
        research_budget_left=followup.research_count_today(session, owner.id)
        < budget.research_per_day,
        max_output_tokens=budget.max_output_tokens,
    )
    cycle.record(
        owner.id,
        action="research",
        executed=result.outcome == "done",
        reason="standing_permission_auto_research",
        goal_id=str(goal.id),
        **result.detail,
    )


def _follow_up_conversation_threads(cycle: _Cycle) -> None:
    """Conversational threads need no web permission. Validate once after an idle interval;
    notifications use the existing quiet hours, daily cap and global pause."""
    threads = cycle.session.scalars(
        select(KnowledgeGap)
        .where(KnowledgeGap.depends_on == "conversation", KnowledgeGap.status == "DEFERRED")
        .order_by(KnowledgeGap.created_at)
    ).all()
    for gap in threads:
        if not cycle.room():
            break
        outcome = consider_followup(
            cycle.session,
            gap=gap,
            provider=cycle.provider,
            now=cycle.now,
            max_output_tokens=cycle.budget.max_output_tokens,
        )
        if outcome is not None:
            cycle.record(
                gap.owner_user_id,
                action="conversation_followup",
                executed=outcome == "notified",
                reason=outcome,
                gap_id=str(gap.id),
            )


def _study(cycle: _Cycle) -> None:
    """A study round is one bounded action, with two separately budgeted model calls."""
    from core.study.service import study_once

    for owner in cycle.active_owners():
        if not cycle.room():
            break
        # The round gets only the time this cycle has left.
        remaining = max(0.001, cycle.budget.max_seconds - cycle.elapsed())
        entry = study_once(
            cycle.session,
            owner=owner,
            provider=cycle.provider,
            search=cycle.search,
            now=cycle.now,
            budget=replace(cycle.budget, max_seconds=remaining),
        )
        if entry is not None:
            cycle.record(
                owner.id,
                action="autonomous_study",
                executed=entry.status == "READY",
                reason=entry.outcome_reason,
                study_id=str(entry.id),
                status=entry.status,
            )


def _reflect_on_finished_conversations(cycle: _Cycle) -> None:
    """Finished conversations not reflected on (reflection only calls the model with evidence)."""
    session = cycle.session
    idle_since = cycle.now - REFLECT_AFTER_IDLE
    candidates = session.scalars(
        select(Conversation).where(Conversation.last_reflected_at.is_(None))
    ).all()
    for conversation in candidates:
        if not cycle.room():
            break
        last = session.scalar(
            select(func.max(Message.created_at)).where(Message.conversation_id == conversation.id)
        )
        if last is None or _aware(last) > idle_since:
            continue
        owner = session.get(User, conversation.user_id)
        result = reflect(
            session,
            conversation=conversation,
            owner=owner,
            provider=cycle.provider,
            max_output_tokens=cycle.budget.max_output_tokens,
        )
        cycle.record(
            owner.id,
            action="reflection",
            executed=result.skipped_reason is None,
            reason=result.skipped_reason or "finished_conversation",
            conversation_id=str(conversation.id),
            created=result.created,
        )


def _consider_the_name_question(cycle: _Cycle) -> None:
    """The identity question left open since genesis (only after real use, rarely)."""
    session, now = cycle.session, cycle.now
    identity = get_identity(session)
    if identity is None or identity.chosen_name is not None or not cycle.room():
        return
    last_event = session.scalar(
        select(func.max(IdentityNameEvent.created_at)).where(
            IdentityNameEvent.identity_id == identity.id
        )
    )
    last_event = _aware(last_event) if last_event else last_event
    conversations = session.scalar(select(func.count()).select_from(Conversation)) or 0
    owner = session.scalar(select(User).order_by(User.created_at).limit(1))
    if (
        owner is None
        or conversations < MIN_CONVERSATIONS_FOR_NAME
        or now - _aware(identity.created_at) < NAME_QUESTION_AFTER
        or (last_event is not None and now - last_event < NAME_QUESTION_EVERY)
    ):
        return
    queued = name_deliberation.request(
        session,
        identity=identity,
        owner=owner,
        reason="questão do nome em aberto desde o genesis",
        now=now,
    )
    session.commit()
    if queued:
        cycle.record(
            owner.id,
            action="name_deliberation_requested",
            executed=True,
            reason="identity_question_open",
        )


def _aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; every stored time is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
