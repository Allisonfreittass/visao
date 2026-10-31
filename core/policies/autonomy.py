"""Global autonomy switch (master prompt §14 and §17: emergency pause for autonomy).

While paused: the worker runs no agent-initiated job, curiosity proposes no goals and no
notification is created. Conversations still work; only what happens on the agent's own
initiative stops.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from infrastructure.database.audit import record_audit
from infrastructure.database.models import SystemFlag

FLAG = "autonomy"


def is_paused(session: Session) -> bool:
    flag = session.get(SystemFlag, FLAG)
    return bool(flag and flag.value.get("paused"))


def set_paused(
    session: Session, paused: bool, *, actor_user_id: uuid.UUID | None, reason: str
) -> None:
    flag = session.get(SystemFlag, FLAG)
    value = {"paused": paused, "reason": reason[:500]}
    if flag is None:
        session.add(SystemFlag(name=FLAG, value=value))
    else:
        flag.value = value
        flag.updated_at = datetime.now(UTC)
    record_audit(
        session,
        "autonomy.pause" if paused else "autonomy.resume",
        "success",
        actor_user_id=actor_user_id,
        details={"reason": reason[:500]},
    )
    session.commit()
