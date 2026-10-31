"""In-app notifications created on the agent's own initiative: rate-limited, held during the
owner's quiet hours, and never created while autonomy is paused."""

import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.policies.autonomy import is_paused
from infrastructure.database.models import Notification, User

MAX_PER_DAY = 5


def _parse(hhmm: str) -> time:
    hours, minutes = hhmm.split(":")
    return time(int(hours), int(minutes))


def deliver_after(user: User, now: datetime) -> datetime:
    """`now` if outside quiet hours, else the end of the current quiet window (UTC)."""
    start, end = _parse(user.quiet_start), _parse(user.quiet_end)
    if start == end:
        return now
    zone = ZoneInfo(user.timezone)
    local = now.astimezone(zone)
    current = local.time()
    crosses_midnight = start > end
    quiet = (current >= start or current < end) if crosses_midnight else (start <= current < end)
    if not quiet:
        return now
    release = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if release <= local:
        release += timedelta(days=1)
    return release.astimezone(UTC)


def notify(
    session: Session,
    *,
    owner: User,
    kind: str,
    title: str,
    body: str,
    goal_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Notification | None:
    """Returns None when paused or over the daily limit (the reason is the caller's to record)."""
    now = now or datetime.now(UTC)
    if is_paused(session):
        return None
    since = now - timedelta(days=1)
    recent = session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.owner_user_id == owner.id, Notification.created_at >= since)
    )
    if (recent or 0) >= MAX_PER_DAY:
        return None
    notification = Notification(
        owner_user_id=owner.id,
        kind=kind,
        title=title[:300],
        body=body[:4000],
        goal_id=goal_id,
        deliver_after=deliver_after(owner, now),
    )
    session.add(notification)
    session.flush()
    return notification
