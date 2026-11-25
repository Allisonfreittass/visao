"""The owner's apps on Composio (docs/APPS.md, ADR-0028): who the owner is there, which apps are
connected, and the Visão's own ceiling on calls a month.

Composio keeps the connections; the Visão keeps only the API key (.env). The owner goes to
Composio as an HMAC of their id with VISION_SECRET_KEY: always the same, with no name or email.
If the server key changes, the old connections are orphaned there and Ajustes asks to connect
again, as with Google."""

import hashlib
import hmac
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from infrastructure.database.audit import record_audit
from infrastructure.database.models import AuditLog
from integrations.composio.client import ComposioClient, ComposioError, Connection

AUDIT_ACTION = "composio_call"
# Gmail and Google Calendar stay on the Visão's own integration (docs/GOOGLE.md): two paths to
# the same email would mean two different approvals for the same thing.
EXCLUDED = frozenset({"gmail", "googlecalendar", "google_calendar"})
CONNECTIONS_TTL_SECONDS = 300
MONTH_OVER = "o limite do mês dos apps acabou"

_CLIENTS: dict[str, ComposioClient] = {}
_CONNECTED: dict[str, tuple[float, list[Connection]]] = {}


class BudgetError(Exception):
    pass


def user_ref(owner_id: uuid.UUID, secret_key: str) -> str:
    digest = hmac.new(
        secret_key.encode(), f"visao-composio-v1:{owner_id}".encode(), hashlib.sha256
    ).hexdigest()
    return f"visao-{digest[:40]}"


def client(api_key: str | None) -> ComposioClient | None:
    """One client per key, so the catalog and tool lists are reused between requests."""
    if not api_key:
        return None
    key = hashlib.sha256(api_key.encode()).hexdigest()
    if key not in _CLIENTS:
        _CLIENTS[key] = ComposioClient(api_key)
    return _CLIENTS[key]


def connected(apps: ComposioClient, owner_ref: str, *, fresh: bool = False) -> list[Connection]:
    """The owner's active apps, Gmail and Calendar left out; kept a few minutes. Empty when
    Composio does not answer: the conversation goes on without apps."""
    kept = _CONNECTED.get(owner_ref)
    if not fresh and kept and time.monotonic() - kept[0] < CONNECTIONS_TTL_SECONDS:
        return kept[1]
    try:
        found = [c for c in apps.connections(owner_ref) if c.toolkit not in EXCLUDED]
    except ComposioError:
        return kept[1] if kept else []
    _CONNECTED[owner_ref] = (time.monotonic(), found)
    return found


def forget(owner_ref: str) -> None:
    """After connecting or disconnecting: the next read asks Composio again."""
    _CONNECTED.pop(owner_ref, None)


def _month_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def calls_this_month(session: Session, now: datetime | None = None) -> int:
    """Every execution counts, all owners and apps together: the plan's limit is the key's."""
    start = _month_start(now or datetime.now(UTC))
    return int(
        session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == AUDIT_ACTION, AuditLog.created_at >= start
            )
        )
        or 0
    )


def spend_call(
    session: Session,
    owner_id: uuid.UUID,
    *,
    toolkit: str,
    tool: str,
    kind: str,
    monthly_limit: int,
) -> AuditLog:
    """Counted before the call goes out, so a crash in the middle still counts. The caller sets
    the outcome. Never the arguments or the result: the audit log keeps no content."""
    if calls_this_month(session) >= monthly_limit:
        raise BudgetError(MONTH_OVER)
    entry = record_audit(
        session,
        AUDIT_ACTION,
        "started",
        actor_user_id=owner_id,
        details={"toolkit": toolkit[:60], "tool": tool[:120], "kind": kind},
    )
    session.flush()
    return entry
