"""After a live quote, the offer to keep it on the home screen and check the price every day
(docs/PAINEIS.md). The reply ends with a short offer, a card with Aprovar shows under it, and a
tap or a plain yes in the next message ("pode", "por favor") accepts it.

Until the live panels exist, accepting writes a page (docs/ARTEFATOS.md) from the same pages read
live, so the offer is already useful.
"""

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.conversation import artifacts
from core.memory.text import fold
from infrastructure.database.models import Artifact, Message, PanelOffer, User

TITLE_CHARS = 60
DEFAULT_TITLE = "Cotação ao vivo"
_PRICE = re.compile(r"(?:R\$|US\$|U\$|€|\bBRL\b|\bUSD\b|\bCLP\b)\s?\d", re.IGNORECASE)
# "até R$ 6 mil", "orçamento de 6.000 reais", "meta de R$ 5.500": the owner's number.
_GOAL = re.compile(
    r"(?:at[ée]|no m[áa]ximo|or[çc]amento(?: de)?|meta(?: de)?|teto(?: de)?|gastar|limite(?: de)?)"
    r"\s*(?:(?:de|pra|para)\s*)?(R\$\s*)?(\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*"
    r"(mil\b|k\b)?\s*(reais)?",
    re.IGNORECASE,
)
_YES = re.compile(
    r"^(?:sim|claro|isso|ok|okay|beleza|pode|pode ser|pode sim|pode fazer|pode criar|quero|"
    r"quero sim|por favor|faz|faca|faz sim|bora|manda ver|com certeza|aceito|fechado|show|"
    r"perfeito|otimo|boa)"
    r"(?: (?:sim|pode|por favor|obrigado|obrigada|valeu|pfv|pf|isso|ai|faz isso|quero))*$"
)
_NO = re.compile(r"\b(?:nao|agora nao|depois|deixa|cancela|nem)\b")


def has_prices(texts: list[str]) -> bool:
    return any(_PRICE.search(t) for t in texts)


def goal_from(*texts: str) -> Decimal | None:
    """The budget the owner named, in code: only with money in sight (R$, mil, reais)."""
    for text in reversed(texts):
        for match in _GOAL.finditer(text):
            money, number, thousand, reais = match.groups()
            if not (money or thousand or reais):
                continue
            digits = number.replace(" ", "").replace(".", "").replace(",", ".")
            try:
                value = Decimal(digits)
            except InvalidOperation:
                continue
            if thousand:
                value *= 1000
            if Decimal(50) <= value <= Decimal(10_000_000):
                return value.quantize(Decimal("0.01"))
    return None


def money(value: Decimal) -> str:
    whole = f"{value:,.0f}" if value == value.to_integral() else f"{value:,.2f}"
    return "R$ " + whole.replace(",", "X").replace(".", ",").replace("X", ".")


def affirmative(text: str) -> bool:
    said = re.sub(r"[^a-z0-9\s]", " ", fold(text))
    said = " ".join(said.split())
    return bool(said) and len(said.split()) <= 6 and not _NO.search(said) and bool(_YES.match(said))


def offer_block(goal: Decimal | None) -> str:
    target = f", e mostre quanto falta para a meta de {money(goal)}" if goal else ""
    return (
        "Você leu preços ao vivo agora. Termine a resposta com uma pergunta curta, em uma frase, "
        "oferecendo deixar essa cotação num painel no Início que confere o preço todo dia"
        + target
        + ". Logo abaixo da resposta aparece um cartão com Aprovar: não diga que o painel já "
        "existe."
    )


def accepted_block(title: str) -> str:
    return (
        f"A pessoa aceitou o painel. A página “{title}”, com a cotação a partir das páginas lidas "
        "ao vivo, está sendo montada agora e aparece aqui num cartão quando ficar pronta. Confirme "
        "em uma frase curta; não diga que já está pronta e não repita os preços."
    )


def propose(
    session: Session,
    *,
    owner: User,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    title: str,
    goal: Decimal | None,
    visit_ids: list[uuid.UUID],
) -> PanelOffer:
    """One offer waits per conversation: a newer quote replaces the older offer."""
    for old in session.scalars(
        select(PanelOffer).where(
            PanelOffer.conversation_id == conversation_id, PanelOffer.status == "proposed"
        )
    ):
        old.status, old.decided_at = "superseded", datetime.now(UTC)
    offer = PanelOffer(
        owner_user_id=owner.id,
        conversation_id=conversation_id,
        message_id=message_id,
        title=(" ".join(title.split())[:TITLE_CHARS].strip(" .:-") or DEFAULT_TITLE),
        goal_amount=goal,
        currency="BRL",
        visit_ids=[str(v) for v in visit_ids],
    )
    session.add(offer)
    session.flush()
    return offer


def pending(session: Session, owner_id: uuid.UUID) -> list[PanelOffer]:
    return list(
        session.scalars(
            select(PanelOffer)
            .where(PanelOffer.owner_user_id == owner_id, PanelOffer.status == "proposed")
            .order_by(PanelOffer.created_at)
        )
    )


def answered_by(session: Session, conversation_id: uuid.UUID, text: str) -> PanelOffer | None:
    """The offer a plain yes accepts: only one made by the latest reply of this conversation,
    so an old card is never accepted by a "pode" about something else."""
    if not affirmative(text):
        return None
    latest = session.scalar(
        select(Message.id)
        .where(Message.conversation_id == conversation_id, Message.role == "assistant")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    if latest is None:
        return None
    return session.scalar(
        select(PanelOffer).where(
            PanelOffer.conversation_id == conversation_id,
            PanelOffer.status == "proposed",
            PanelOffer.message_id == latest,
        )
    )


def own(session: Session, owner_id: uuid.UUID, offer_id: uuid.UUID) -> PanelOffer:
    offer = session.get(PanelOffer, offer_id)
    if offer is None or offer.owner_user_id != owner_id or offer.status != "proposed":
        raise LookupError("offer")
    return offer


def accept(
    session: Session, offer: PanelOffer, owner: User, conversation, message_id: uuid.UUID
) -> Artifact:
    """For now a page from the same live pages; the build runs in the background (the caller)."""
    page = artifacts.create(
        session,
        owner=owner,
        conversation=conversation,
        message_id=message_id,
        request=artifacts.Request(title=offer.title),
    )
    offer.status, offer.decided_at, offer.artifact_id = "accepted", datetime.now(UTC), page.id
    return page


def reject(offer: PanelOffer) -> None:
    offer.status, offer.decided_at = "rejected", datetime.now(UTC)
