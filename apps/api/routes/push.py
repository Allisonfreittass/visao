"""Opt-in Web Push: the browser subscribes here so an opening reaches it with the app closed."""

import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.deps import AppSettings, CurrentUser, DbSession, SessionFactory
from apps.api.push import enabled
from core.initiatives import push
from infrastructure.database.audit import record_audit
from infrastructure.database.models import PushSubscription
from integrations.push.webpush import allowed_endpoint

router = APIRouter(prefix="/push", tags=["push"])

MAX_SUBSCRIPTIONS = 10
# On iPhone an aviso that arrives with the app open may not show: the test waits this long at
# most, so there is time to lock the phone first.
MAX_TEST_DELAY_SECONDS = 15


class LastDelivery(BaseModel):
    at: datetime
    # success | failed | no_device | disabled
    outcome: str
    devices: int = 0
    sent: int = 0
    errors: list[str] = []


class PushStatus(BaseModel):
    enabled: bool
    public_key: str | None
    subscriptions: int
    last_delivery: LastDelivery | None = None


class Keys(BaseModel):
    model_config = ConfigDict(extra="ignore")

    p256dh: str = Field(min_length=16, max_length=255)
    auth: str = Field(min_length=8, max_length=255)


class SubscriptionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint: str = Field(max_length=2048)
    keys: Keys


class EndpointIn(BaseModel):
    endpoint: str = Field(max_length=2048)


class TestOut(BaseModel):
    sent: int
    # Devices a delayed test will go to; it is sent after the response.
    scheduled: int = 0


def _count(db: DbSession, user: CurrentUser) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(PushSubscription)
            .where(PushSubscription.owner_user_id == user.id)
        )
        or 0
    )


@router.get("", response_model=PushStatus)
def status_(user: CurrentUser, db: DbSession, settings: AppSettings) -> PushStatus:
    on = enabled(settings)
    entry = push.last_delivery(db, user.id)
    last = None
    if entry is not None:
        details = entry.details or {}
        at = entry.created_at if entry.created_at.tzinfo else entry.created_at.replace(tzinfo=UTC)
        last = LastDelivery(
            at=at,
            outcome=entry.outcome,
            devices=int(details.get("devices", 0)),
            sent=int(details.get("sent", 0)),
            errors=[str(e) for e in details.get("errors", [])][:5],
        )
    return PushStatus(
        enabled=on,
        public_key=settings.webpush_public_key if on else None,
        subscriptions=_count(db, user),
        last_delivery=last,
    )


@router.post("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def subscribe(
    body: SubscriptionIn, request: Request, user: CurrentUser, db: DbSession, settings: AppSettings
) -> None:
    if not enabled(settings):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Avisos push não configurados")
    if not allowed_endpoint(body.endpoint):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Serviço de push desconhecido")
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if existing is not None and existing.owner_user_id != user.id:
        # A browser belongs to whoever subscribed it last on this device.
        db.delete(existing)
        db.flush()
        existing = None
    if existing is None:
        if _count(db, user) >= MAX_SUBSCRIPTIONS:
            raise HTTPException(status.HTTP_409_CONFLICT, "Limite de aparelhos atingido")
        existing = PushSubscription(owner_user_id=user.id, endpoint=body.endpoint)
        db.add(existing)
    existing.p256dh = body.keys.p256dh
    existing.auth = body.keys.auth
    existing.user_agent = request.headers.get("user-agent", "")[:255]
    existing.failures = 0
    existing.created_at = existing.created_at or datetime.now(UTC)
    record_audit(db, "push.subscribe", "success", actor_user_id=user.id)
    db.commit()


@router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(body: EndpointIn, user: CurrentUser, db: DbSession) -> None:
    db.execute(
        delete(PushSubscription).where(
            PushSubscription.owner_user_id == user.id, PushSubscription.endpoint == body.endpoint
        )
    )
    record_audit(db, "push.unsubscribe", "success", actor_user_id=user.id)
    db.commit()


TEST_TITLE = "Teste de aviso"
TEST_BODY = "Se isto chegou com o app fechado, eu consigo te chamar."


def _send_test(db: Session, owner_id: uuid.UUID) -> int:
    return push.send_to_owner(db, owner_id, title=TEST_TITLE, body=TEST_BODY, tag="visao-test")


def _send_test_later(factory: sessionmaker[Session], owner_id: uuid.UUID, delay: int) -> None:
    time.sleep(delay)
    with factory() as session:
        _send_test(session, owner_id)
        session.commit()


@router.post("/test", response_model=TestOut)
def test(
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    factory: SessionFactory,
    background: BackgroundTasks,
    delay: int = Query(0, ge=0, le=MAX_TEST_DELAY_SECONDS),
) -> TestOut:
    if not enabled(settings) or not push.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Avisos push não configurados")
    if delay:
        background.add_task(_send_test_later, factory, user.id, delay)
        return TestOut(sent=0, scheduled=_count(db, user))
    sent = _send_test(db, user.id)
    db.commit()
    return TestOut(sent=sent)
