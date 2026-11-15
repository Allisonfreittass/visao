"""Panel offers (docs/PAINEIS.md): after a live quote, the card that waits for a yes."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel

from apps.api.deps import AppSettings, CurrentUser, DbSession, SessionFactory
from apps.api.routes.artifacts import ArtifactOut, artifact_out, build_in_background
from apps.api.routes.conversations import OptionalProvider, _budgets
from core.identity.genesis import get_identity
from core.panels import offers
from infrastructure.database.audit import record_audit
from infrastructure.database.models import Conversation, PanelOffer

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
    artifact: ArtifactOut | None = None
    created_at: datetime


def offer_out(offer: PanelOffer, page=None) -> OfferOut:
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
        artifact=artifact_out(page) if page is not None else None,
        created_at=offer.created_at,
    )


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
    factory: SessionFactory,
    background: BackgroundTasks,
    via: Literal["toque", "voz"] = "toque",
) -> OfferOut:
    try:
        offer = offers.own(db, user.id, offer_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "oferta não encontrada") from exc
    page = None
    if decision == "approve":
        if provider is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM não configurado")
        conversation = db.get(Conversation, offer.conversation_id)
        if conversation is None or offer.message_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "conversa não encontrada")
        page = offers.accept(db, offer, user, conversation, offer.message_id)
        identity = get_identity(db)
        background.add_task(
            build_in_background,
            factory,
            page.id,
            provider,
            settings,
            _budgets(settings),
            identity.chosen_name if identity else None,
            "",
        )
    else:
        offers.reject(offer)
    record_audit(
        db,
        f"panel_offer.{decision}",
        "success",
        actor_user_id=user.id,
        details={"via": via, "offer_id": str(offer.id)},
    )
    db.commit()
    return offer_out(offer, page)
