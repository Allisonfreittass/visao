"""Opt-in Web Push: the browser subscribes here so an opening reaches it with the app closed."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

from apps.api.deps import AppSettings, CurrentUser, DbSession
from apps.api.push import enabled
from core.initiatives import push
from infrastructure.database.audit import record_audit
from infrastructure.database.models import PushSubscription
from integrations.push.webpush import allowed_endpoint

router = APIRouter(prefix="/push", tags=["push"])

MAX_SUBSCRIPTIONS = 10


class PushStatus(BaseModel):
    enabled: bool
    public_key: str | None
    subscriptions: int


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
    return PushStatus(
        enabled=on,
        public_key=settings.webpush_public_key if on else None,
        subscriptions=_count(db, user),
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


@router.post("/test", response_model=TestOut)
def test(user: CurrentUser, db: DbSession, settings: AppSettings) -> TestOut:
    if not enabled(settings) or not push.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Avisos push não configurados")
    sent = push.send_to_owner(
        db,
        user.id,
        title="Teste de aviso",
        body="Se isto chegou com o app fechado, eu consigo te chamar.",
        tag="visao-test",
    )
    db.commit()
    return TestOut(sent=sent)
