"""Audited naming decisions (docs/AUTONOMOUS_NAMING.md).

Only the agent's deliberation mechanism may call `record_naming_decision`. No API endpoint, seed
or prompt sets a name; the user cannot assign one. A missing name blocks nothing.
"""

import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.database.audit import record_audit
from infrastructure.database.models import AgentIdentity, IdentityNameEvent

MAX_NAME_LENGTH = 64


class NameEventType(StrEnum):
    CHOSEN = "CHOSEN"
    CHANGED = "CHANGED"
    DEFERRED = "DEFERRED"
    DECLINED = "DECLINED"


@dataclass(frozen=True)
class NamingDecision:
    action: Literal["choose", "defer", "decline"]
    context_summary: str
    rationale_summary: str
    model_provider: str
    model_version: str
    name: str | None = None
    alternatives_considered: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def normalize_name(raw: str) -> str:
    name = unicodedata.normalize("NFC", raw).strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"name must have 1 to {MAX_NAME_LENGTH} characters")
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        raise ValueError("name must not contain control characters")
    return name


def _event_type(decision: NamingDecision, previous: str | None) -> NameEventType:
    if decision.action == "defer":
        return NameEventType.DEFERRED
    if decision.action == "decline":
        return NameEventType.DECLINED
    return NameEventType.CHOSEN if previous is None else NameEventType.CHANGED


def record_naming_decision(
    session: Session, identity: AgentIdentity, decision: NamingDecision
) -> IdentityNameEvent:
    """Writes the event and, for a choice, updates `chosen_name` in the same transaction."""
    for label, value in (
        ("context_summary", decision.context_summary),
        ("rationale_summary", decision.rationale_summary),
        ("model_provider", decision.model_provider),
        ("model_version", decision.model_version),
    ):
        if not value.strip():
            raise ValueError(f"{label} is required")

    previous = identity.chosen_name
    new_name: str | None = None
    if decision.action == "choose":
        if decision.name is None:
            raise ValueError("a choice needs a name")
        new_name = normalize_name(decision.name)
        if new_name == previous:
            raise ValueError("name is unchanged")
    elif decision.name is not None:
        raise ValueError("only a choice carries a name")

    event = IdentityNameEvent(
        identity_id=identity.id,
        event_type=_event_type(decision, previous),
        previous_name=previous,
        new_name=new_name,
        alternatives_considered=list(decision.alternatives_considered),
        context_summary=decision.context_summary,
        sources=list(decision.sources),
        rationale_summary=decision.rationale_summary,
        model_provider=decision.model_provider,
        model_version=decision.model_version,
    )
    session.add(event)
    if new_name is not None:
        identity.chosen_name = new_name
    record_audit(
        session,
        "identity.naming_decision",
        "success",
        details={"identity_id": str(identity.id), "event_type": event.event_type},
    )
    session.commit()
    return event


def name_history(session: Session, identity: AgentIdentity) -> list[IdentityNameEvent]:
    """Names the agent has held, oldest first. Deferrals and refusals are not names."""
    return list(
        session.scalars(
            select(IdentityNameEvent)
            .where(
                IdentityNameEvent.identity_id == identity.id,
                IdentityNameEvent.event_type.in_([NameEventType.CHOSEN, NameEventType.CHANGED]),
            )
            .order_by(IdentityNameEvent.created_at)
        )
    )
