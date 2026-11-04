"""The agent starting a conversation: a real chat message, not a notification.

Persistence without nagging: it stays quiet during quiet hours and while the owner is mid-
conversation, and it stops after two unanswered openings until the owner replies.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.identity.genesis import get_identity
from core.initiatives.notify import deliver_after
from core.policies.autonomy import is_paused
from infrastructure.database.models import Conversation, Message, Notification, User

MIN_IDLE = timedelta(minutes=15)
MAX_UNANSWERED = 2


@dataclass(frozen=True)
class Delivery:
    sent: bool
    reason: str
    message: Message | None = None


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _owner_messages(session: Session, owner: User):
    return (
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.user_id == owner.id)
    )


def last_owner_message_at(session: Session, owner: User) -> datetime | None:
    value = session.scalar(
        select(func.max(Message.created_at))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.user_id == owner.id, Message.role == "user")
    )
    return _utc(value) if value else None


def unanswered(session: Session, owner: User) -> int:
    """Initiative messages since the owner last spoke."""
    since = last_owner_message_at(session, owner)
    query = select(func.count()).select_from(
        _owner_messages(session, owner).where(Message.origin == "initiative").subquery()
    )
    if since is not None:
        query = select(func.count()).select_from(
            _owner_messages(session, owner)
            .where(Message.origin == "initiative", Message.created_at > since)
            .subquery()
        )
    return session.scalar(query) or 0


def can_speak(session: Session, owner: User, now: datetime, per_day: int) -> str | None:
    """None when it may speak now, otherwise the reason it stays quiet."""
    if is_paused(session):
        return "paused"
    if deliver_after(owner, now) > now:
        return "quiet_hours"
    last = last_owner_message_at(session, owner)
    if last is not None and now - last < MIN_IDLE:
        return "owner_active"
    if unanswered(session, owner) >= MAX_UNANSWERED:
        return "waiting_for_reply"
    sent_today = session.scalar(
        select(func.count()).select_from(
            _owner_messages(session, owner)
            .where(Message.origin == "initiative", Message.created_at >= now - timedelta(days=1))
            .subquery()
        )
    )
    if (sent_today or 0) >= per_day:
        return "daily_limit"
    return None


def post(session: Session, owner: User, text: str, now: datetime, per_day: int) -> Delivery:
    reason = can_speak(session, owner, now, per_day)
    if reason is not None:
        return Delivery(False, reason)
    conversation = session.scalar(
        select(Conversation)
        .where(Conversation.user_id == owner.id)
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    if conversation is None:
        identity = get_identity(session)
        if identity is None:
            return Delivery(False, "no_identity")
        conversation = Conversation(user_id=owner.id, identity_id=identity.id)
        session.add(conversation)
        session.flush()
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=text[:2000],
        origin="initiative",
        created_at=now,
    )
    session.add(message)
    session.add(
        Notification(
            owner_user_id=owner.id,
            kind="initiative",
            title="Puxou conversa",
            body=text[:4000],
            deliver_after=now,
            created_at=now,
        )
    )
    session.flush()
    return Delivery(True, "sent", message)
