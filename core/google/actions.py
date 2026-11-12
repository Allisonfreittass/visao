"""Email to send and events to schedule: proposed by the agent, shown in full, run only after the
owner approves. The approval shows exactly what goes out (recipient, subject, text, time,
guests), so an email that tries to give orders can at most produce a proposal the owner reads."""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.google import account as accounts
from core.initiatives import push
from infrastructure.database.models import Conversation, GoogleAction, Message, User
from integrations.google.client import GoogleError

MAX_PENDING = 5


class ActionError(ValueError):
    pass


def _clean(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _zone(owner: User) -> ZoneInfo:
    try:
        return ZoneInfo(owner.timezone or "America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Sao_Paulo")


def _pending(session: Session, owner_id: uuid.UUID) -> list[GoogleAction]:
    return list(
        session.scalars(
            select(GoogleAction)
            .where(GoogleAction.owner_user_id == owner_id, GoogleAction.status == "proposed")
            .order_by(GoogleAction.created_at)
        )
    )


def _add(session, owner_id, conversation_id, kind, payload) -> GoogleAction:
    if len(_pending(session, owner_id)) >= MAX_PENDING:
        raise ActionError("já há pedidos demais esperando você")
    action = GoogleAction(
        owner_user_id=owner_id,
        conversation_id=conversation_id,
        kind=kind,
        payload=payload,
        status="proposed",
        result="",
        created_at=datetime.now(UTC),
    )
    session.add(action)
    session.flush()
    return action


def propose_email(
    session: Session,
    owner_id: uuid.UUID,
    *,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    conversation_id: uuid.UUID | None = None,
) -> GoogleAction:
    to, subject, body = _clean(to, 320), _clean(subject, 300), _clean(body, 8000)
    if "@" not in to or not body:
        raise ActionError("falta destinatário ou texto")
    payload = {"to": to, "subject": subject or "(sem assunto)", "body": body}
    if reply_to:
        payload["reply_to"] = _clean(reply_to, 100)
    return _add(session, owner_id, conversation_id, "send_email", payload)


def propose_event(
    session: Session,
    owner: User,
    *,
    title: str,
    start: str,
    end: str | None = None,
    location: str = "",
    description: str = "",
    attendees: list[str] | None = None,
    conversation_id: uuid.UUID | None = None,
) -> GoogleAction:
    zone = _zone(owner)
    try:
        begins = datetime.fromisoformat(start)
        ends = datetime.fromisoformat(end) if end else begins + timedelta(hours=1)
    except (TypeError, ValueError) as exc:
        raise ActionError("data ou hora inválida") from exc
    begins = begins if begins.tzinfo else begins.replace(tzinfo=zone)
    ends = ends if ends.tzinfo else ends.replace(tzinfo=zone)
    now = datetime.now(UTC)
    if not (now - timedelta(hours=1) < begins < now + timedelta(days=730)):
        raise ActionError("o evento precisa ser no futuro, nos próximos dois anos")
    if not timedelta(minutes=5) <= ends - begins <= timedelta(hours=24):
        raise ActionError("o evento precisa durar entre 5 minutos e 24 horas")
    guests = [a.strip() for a in (attendees or []) if isinstance(a, str) and "@" in a][:20]
    payload = {
        "title": _clean(title, 300) or "(sem título)",
        "start": begins.isoformat(),
        "end": ends.isoformat(),
        "timezone": str(zone),
        "location": _clean(location, 300),
        "description": _clean(description, 4000),
        "attendees": guests,
    }
    return _add(session, owner.id, conversation_id, "create_event", payload)


def describe(action: GoogleAction) -> str:
    p = action.payload
    if action.kind == "send_email":
        return f"Email para {p['to']}: {p['subject']}"
    when = datetime.fromisoformat(p["start"]).strftime("%d/%m %H:%M")
    guests = f", com {', '.join(p['attendees'])}" if p.get("attendees") else ""
    return f"Evento: {p['title']}, {when}{guests}"


def _owned(session: Session, owner_id: uuid.UUID, action_id: uuid.UUID) -> GoogleAction:
    action = session.get(GoogleAction, action_id)
    if action is None or action.owner_user_id != owner_id:
        raise LookupError("action")
    return action


def _report(session: Session, action: GoogleAction, text: str) -> None:
    """What happened goes back into the conversation it came from, as its message."""
    conversation = (
        session.get(Conversation, action.conversation_id) if action.conversation_id else None
    )
    if conversation is not None:
        session.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=text,
                origin="google",
                created_at=datetime.now(UTC),
            )
        )


def reject(session: Session, owner_id: uuid.UUID, action_id: uuid.UUID) -> GoogleAction:
    action = _owned(session, owner_id, action_id)
    if action.status == "proposed":
        action.status, action.decided_at = "rejected", datetime.now(UTC)
        session.flush()
    return action


def approve(session: Session, owner: User, action_id: uuid.UUID, secret_key: str) -> GoogleAction:
    action = _owned(session, owner.id, action_id)
    if action.status != "proposed":
        return action
    action.decided_at = datetime.now(UTC)
    account = accounts.get(session, owner.id)
    google = accounts.client_for(account, secret_key) if account is not None else None
    if google is None:
        action.status, action.result = "failed", "O Google não está conectado."
        session.flush()
        return action
    p = action.payload
    try:
        if action.kind == "send_email":
            original = google.headers(p["reply_to"]) if p.get("reply_to") else None
            subject = p["subject"]
            if original is not None and not subject.lower().startswith("re:"):
                subject = f"Re: {original.subject}" if original.subject else subject
            google.send(to=p["to"], subject=subject, body=p["body"], reply_to=original)
            action.result = f"Mandei o email para {p['to']}: {subject}."
        else:
            event = google.create_event(
                title=p["title"],
                start=datetime.fromisoformat(p["start"]),
                end=datetime.fromisoformat(p["end"]),
                timezone=p["timezone"],
                description=p.get("description", ""),
                location=p.get("location", ""),
                attendees=tuple(p.get("attendees", [])),
            )
            when = datetime.fromisoformat(p["start"]).strftime("%d/%m às %H:%M")
            action.result = f"Marquei na sua agenda: {event.title}, {when}."
        action.status = "done"
    except GoogleError as exc:
        accounts.note_failure(session, account, exc)
        action.status, action.result = "failed", f"Não deu: {exc}."
    _report(session, action, action.result)
    session.flush()
    if action.status == "done" and action.conversation_id is None:
        push.send_to_owner(session, owner.id, title="Feito", body=action.result, url="/")
    return action


def pending(session: Session, owner_id: uuid.UUID) -> list[GoogleAction]:
    return _pending(session, owner_id)
