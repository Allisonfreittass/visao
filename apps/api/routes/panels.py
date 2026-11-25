"""Live panels on the home screen (docs/PAINEIS.md, ADR-0012): the offer card after a live quote,
the panels themselves (pause, delete, history) and the suggestions when there is nothing yet."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from apps.api.deps import AppSettings, CurrentUser, DbSession
from apps.api.limits import panel_limits
from apps.api.routes.conversations import OptionalProvider
from core.panels import offers
from core.panels import service as panels
from core.panels.suggestions import suggestions
from infrastructure.database.audit import record_audit
from infrastructure.database.models import Conversation, Panel, PanelOffer

router = APIRouter(prefix="/panels", tags=["panels"])


class OfferOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None
    title: str
    goal_amount: Decimal | None
    currency: str
    status: str
    # What the card says.
    summary: str
    panel_id: uuid.UUID | None = None
    created_at: datetime


class ItemOut(BaseModel):
    kind: str
    provider: str
    where: str
    dates: str
    connections: int | None
    price: Decimal | None
    price_basis: str
    cost: Decimal | None
    currency: str
    site: str
    url: str
    read_at: datetime | None


class PanelOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    status: str
    spec: dict[str, Any]
    total: Decimal | None
    goal: Decimal | None
    goal_gap: Decimal | None
    # "R$ 555 acima da meta de R$ 6.000", or, with part of the quote, "parcial de R$ 164 na meta
    # de R$ 4.000: sobram R$ 3.836 para voo"; computed here.
    goal_words: str | None
    # While the total is "a confirmar": the sum of what is priced and what still has no price.
    partial: Decimal | None = None
    missing: list[str] = []
    quoted: int = 0
    change: Decimal | None
    items: list[ItemOut]
    checked_at: datetime | None
    # False: the numbers are from an earlier day; the card says when, never "agora".
    checked_today: bool
    next_check_at: datetime | None
    # Near the goal it is checked every this many hours (outside quiet hours); null: once a day.
    watch_every_hours: int | None = None
    note: str
    conversation_id: uuid.UUID | None
    # The project it belongs to (shown inside that project too, ADR-0021); null: none.
    project_id: uuid.UUID | None = None
    created_at: datetime


class PointOut(BaseModel):
    total: Decimal | None
    checked_at: datetime


class PanelDetailOut(PanelOut):
    history: list[PointOut]


class PanelPatch(BaseModel):
    status: Literal["active", "paused"]


class SuggestionOut(BaseModel):
    text: str
    draft: str


def offer_out(offer: PanelOffer, panel_id: uuid.UUID | None = None) -> OfferOut:
    goal = (
        f", com a distância da meta de {offers.money(offer.goal_amount)}"
        if offer.goal_amount
        else ""
    )
    return OfferOut(
        id=offer.id,
        conversation_id=offer.conversation_id,
        message_id=offer.message_id,
        title=offer.title,
        goal_amount=offer.goal_amount,
        currency=offer.currency,
        status=offer.status,
        summary=f"Deixar “{offer.title}” no Início{goal}, conferindo o preço todo dia",
        panel_id=panel_id,
        created_at=offer.created_at,
    )


def panel_out(db, panel: Panel, user, limits: panels.Limits) -> PanelOut:
    shown = panels.card(db, panel, user, limits=limits)
    return PanelOut(**shown)


def _own(db, user_id: uuid.UUID, panel_id: uuid.UUID) -> Panel:
    panel = db.get(Panel, panel_id)
    if panel is None or panel.owner_user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Painel não encontrado")
    return panel


@router.get("/offers")
def list_offers(db: DbSession, user: CurrentUser) -> list[OfferOut]:
    return [offer_out(o) for o in offers.pending(db, user.id)]


@router.post("/offers/{offer_id}/{decision}")
def decide(
    offer_id: uuid.UUID,
    decision: Literal["approve", "reject"],
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: OptionalProvider,
    via: Literal["toque", "voz"] = "toque",
) -> OfferOut:
    try:
        offer = offers.own(db, user.id, offer_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "oferta não encontrada") from exc
    if decision == "reject":
        offers.reject(offer)
        record_audit(
            db, "panel_offer.reject", "success", actor_user_id=user.id, details={"via": via}
        )
        db.commit()
        return offer_out(offer)
    if provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM não configurado")
    conversation = db.get(Conversation, offer.conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversa não encontrada")
    limits = panel_limits(settings)
    try:
        panel = panels.create_from_offer(
            db,
            offer=offer,
            owner=user,
            conversation=conversation,
            provider=provider,
            limits=limits,
            via=via,
        )
    except panels.LimitReached as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Você já tem {limits.max_active} painéis ativos. Pause ou apague um no Início.",
        ) from exc
    return offer_out(offer, panel.id)


@router.get("")
def list_panels(db: DbSession, user: CurrentUser, settings: AppSettings) -> list[PanelOut]:
    rows = db.query(Panel).filter(Panel.owner_user_id == user.id).order_by(Panel.created_at)
    limits = panel_limits(settings)
    return [panel_out(db, p, user, limits) for p in rows if p.status != "expired"]


@router.get("/suggestions")
def list_suggestions(db: DbSession, user: CurrentUser) -> list[SuggestionOut]:
    return [SuggestionOut(**s) for s in suggestions(db, user)]


@router.get("/{panel_id}")
def panel_detail(
    panel_id: uuid.UUID, db: DbSession, user: CurrentUser, settings: AppSettings
) -> PanelDetailOut:
    panel = _own(db, user.id, panel_id)
    out = panel_out(db, panel, user, panel_limits(settings))
    return PanelDetailOut(
        **out.model_dump(), history=[PointOut(**h) for h in panels.history(db, panel)]
    )


@router.patch("/{panel_id}")
def pause_or_resume(
    panel_id: uuid.UUID, body: PanelPatch, db: DbSession, user: CurrentUser, settings: AppSettings
) -> PanelOut:
    """Paused: no check, no notices. Resumed: checked again next morning, or in a few hours when
    near the goal."""
    panel = _own(db, user.id, panel_id)
    if panel.status == "expired":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esse painel já expirou")
    panel.status = body.status
    if body.status == "active":
        panels.rewatch(db, panel, user, panel_limits(settings), told=False)
    else:
        panel.next_check_at = None
    record_audit(
        db,
        f"panel.{'resume' if body.status == 'active' else 'pause'}",
        "success",
        actor_user_id=user.id,
        details={"panel_id": str(panel.id)},
    )
    db.commit()
    return panel_out(db, panel, user, panel_limits(settings))


@router.delete("/{panel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_panel(panel_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    panel = _own(db, user.id, panel_id)
    db.delete(panel)
    record_audit(
        db, "panel.delete", "success", actor_user_id=user.id, details={"panel_id": str(panel_id)}
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
