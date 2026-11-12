"""Sends an opening to the owner's subscribed browsers, so it arrives with the app closed.

Only openings that already passed every rule in `core/mind/initiative.py` (quiet hours, pause,
owner active, unanswered limit, daily limit) get here, so a push adds no new way to nag. Failure
never blocks the opening itself: the message is in the chat either way.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from infrastructure.database.models import PushSubscription
from integrations.push.webpush import PushSender, Subscription

MAX_FAILURES = 5
BODY_CHARS = 180

logger = logging.getLogger(__name__)


# Set once at startup by the process that runs the agent (API or worker), from its settings; core
# never reads configuration itself. None = push disabled, which is the default.
_sender: PushSender | None = None


def configure(sender: PushSender | None) -> None:
    global _sender
    _sender = sender


def configured() -> bool:
    return _sender is not None


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= BODY_CHARS else text[: BODY_CHARS - 1].rstrip() + "…"


def send_to_owner(
    session: Session,
    owner_id: uuid.UUID,
    *,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "visao-opening",
    now: datetime | None = None,
) -> int:
    """Returns how many browsers accepted it. Drops subscriptions the push service says are gone
    and those that keep failing."""
    sender = _sender
    if sender is None:
        return 0
    now = now or datetime.now(UTC)
    rows = session.scalars(
        select(PushSubscription).where(PushSubscription.owner_user_id == owner_id)
    ).all()
    payload = {"title": title[:80], "body": _short(body), "url": url, "tag": tag}
    sent = 0
    for row in rows:
        result = sender.send(Subscription(row.endpoint, row.p256dh, row.auth), payload)
        if result.ok:
            row.failures = 0
            row.last_sent_at = now
            sent += 1
            continue
        row.failures += 1
        logger.warning("push failed: %s", result.detail, extra={"event": "push_failed"})
        if result.gone or row.failures >= MAX_FAILURES:
            session.execute(delete(PushSubscription).where(PushSubscription.id == row.id))
    session.flush()
    return sent
