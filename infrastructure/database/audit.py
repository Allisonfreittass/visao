import uuid
from typing import Any

from sqlalchemy.orm import Session

from infrastructure.database.models import AuditLog


def record_audit(
    session: Session,
    action: str,
    outcome: str,
    actor_user_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Adds an audit entry to the session; the caller owns the commit."""
    entry = AuditLog(
        actor_user_id=actor_user_id, action=action, outcome=outcome, details=details or {}
    )
    session.add(entry)
    return entry
