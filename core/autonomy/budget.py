"""The daily autonomy budget, and the one way an autonomous step may call the model.

Everything the agent does without a new message (thinking, reviewing, studying, proposing code)
shares one ledger: a cap on calls and tokens per UTC day for the autonomous purposes, plus the
global daily spend. A step asks ``has_room`` before it starts and goes through
``complete_json``, which re-checks the budget, records the call before it is made and refuses
output that is truncated or not a single JSON object.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from infrastructure.database.models import ModelUsage
from integrations.llm.base import ChatMessage, LLMError, LLMProvider

AUTONOMOUS_PURPOSES = (
    "code_proposal",
    "mind_review",
    "mind_think",
    "name_deliberation",
    "followup_summary",
    "reflection",
    "conversation_followup",
    "study_plan",
    "study_review",
)


@dataclass(frozen=True)
class AutonomyBudget:
    llm_calls_per_day: int
    tokens_per_day: int
    max_actions_per_cycle: int
    max_seconds: float
    research_per_day: int
    max_output_tokens: int
    daily_usd: Decimal = Decimal("1.50")
    study_interval: timedelta = timedelta(hours=6)
    open_web: bool = False
    mind: Any = None  # core.mind.think.MindConfig when the inner loop is on


def start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def usage_today(session: Session, now: datetime) -> tuple[int, int]:
    """Autonomous model calls and tokens recorded since the start of ``now``'s day."""
    row = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(ModelUsage.input_tokens + ModelUsage.output_tokens), 0),
        ).where(
            ModelUsage.purpose.in_(AUTONOMOUS_PURPOSES),
            ModelUsage.created_at >= start_of_day(now),
        )
    ).one()
    return int(row[0]), int(row[1])


def budget_left(session: Session, budget: AutonomyBudget, now: datetime) -> bool:
    """At least one more autonomous call fits under today's call and token caps."""
    calls, tokens = usage_today(session, now)
    return calls < budget.llm_calls_per_day and tokens < budget.tokens_per_day


def has_room(session: Session, budget: AutonomyBudget, now: datetime, calls: int = 1) -> bool:
    """``calls`` more autonomous calls fit today, and total spend is under the daily USD cap.

    The spend counts every purpose, conversations included: autonomy never eats the money a
    reply would need.
    """
    used, _ = usage_today(session, now)
    spent = session.scalar(
        select(func.coalesce(func.sum(ModelUsage.cost_usd), 0)).where(
            ModelUsage.created_at >= start_of_day(now)
        )
    )
    return (
        used + calls <= budget.llm_calls_per_day
        and budget_left(session, budget, now)
        and Decimal(str(spent)) < budget.daily_usd
    )


def parse_json_object(text: str) -> dict:
    """One JSON object, optionally inside a ```json fence; never a partial extraction."""
    cleaned = text.strip()
    if cleaned.startswith("```json") and cleaned.endswith("```"):
        cleaned = cleaned[7:-3].strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("invalid_schema")
    return data


def complete_json(
    session: Session,
    provider: LLMProvider,
    purpose: str,
    prompt: list[ChatMessage],
    budget: AutonomyBudget,
    now: datetime,
) -> dict:
    """Make one budgeted model call and return its reply as a JSON object.

    Raises ``ValueError("autonomy_budget")`` when there is no room, re-raises ``LLMError``
    from the provider, and raises ``ValueError("invalid_model_output")`` for a truncated or
    malformed reply. Every outcome is written to ``ModelUsage``.
    """
    if not has_room(session, budget, now):
        raise ValueError("autonomy_budget")
    usage = ModelUsage(
        purpose=purpose, provider=provider.name, model=provider.model, outcome="pending"
    )
    session.add(usage)
    session.commit()  # a crash/failed call still counts toward the call limit
    try:
        response = provider.complete(prompt, max_output_tokens=budget.max_output_tokens)
    except LLMError as exc:
        usage.outcome, usage.error_kind = "error", exc.kind[:50]
        session.commit()
        raise
    usage.provider, usage.model = response.provider, response.model
    usage.input_tokens, usage.output_tokens = response.input_tokens, response.output_tokens
    usage.cost_usd, usage.latency_ms = response.cost_usd, response.latency_ms
    try:
        if response.finish_reason == "length":
            raise ValueError("truncated_output")
        data = parse_json_object(response.text)
    except ValueError:
        usage.outcome = "bad_output"
        session.commit()
        raise ValueError("invalid_model_output") from None
    usage.outcome = "success"
    session.commit()
    return data
