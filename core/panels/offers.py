"""After a live quote, the offer to keep it on the home screen and check the price every day
(docs/PAINEIS.md). The reply ends with a short offer, a card with Aprovar shows under it, and a
tap or a plain yes in the next message ("pode", "por favor") accepts it.

Accepting creates the live panel (core/panels/service.py) from the same pages read live.
"""

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.memory.text import fold
from infrastructure.database.models import Message, PanelOffer, User

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
# "me avisa se ficar abaixo de R$ 2.000", "me avisa se cair pra 2 mil": a goal said as a notice.
_ALERT_GOAL = re.compile(
    r"\b(?:avis\w*|alert\w*|notific\w*|me (?:fala|diz|chama))\b[^.?!\n]{0,40}?"
    r"\b(?:abaixo d[eo]|menos d[eo]|baix(?:ar|ou|e|a)|ca(?:ir|iu|ia)|cheg(?:ar|ue|a))"
    r"\s*(?:(?:a|em|de|pra|para|at[ée])\s*)?(R\$\s*)?"
    r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(mil\b|k\b)?\s*(reais)?",
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


def alert_goal(text: str) -> str | None:
    """What is left of the message around "me avisa se cair pra R$ 2 mil", or None without one."""
    match = _ALERT_GOAL.search(text)
    return None if match is None else (text[: match.start()] + " " + text[match.end() :]).strip()


def goal_from(*texts: str) -> Decimal | None:
    """The budget the owner named, in code: only with money in sight (R$, mil, reais). "Me avisa
    se ficar abaixo de R$ 2.000" names one too."""
    for text in reversed(texts):
        matches = [*_ALERT_GOAL.finditer(text), *_GOAL.finditer(text)]
        for match in matches:
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


def ready_block(title: str, total: str | None, gap: str | None) -> str:
    """For the reply right after the panel was created from the owner's yes."""
    numbers = f" Total agora: {total}." if total else " Os preços ainda estão a confirmar."
    distance = f" {gap}." if gap else ""
    return (
        f"A pessoa aceitou, e o painel “{title}” já está no Início, com a cotação lida ao vivo."
        f"{numbers}{distance} Ele confere o preço uma vez por dia e avisa se mudar algo "
        "importante. Confirme em uma ou duas bolhas curtas, sem repetir a cotação inteira."
    )


def limit_block(limit: int) -> str:
    return (
        f"A pessoa aceitou o painel, mas ela já tem {limit} painéis ativos, o limite. Nada foi "
        "criado. Diga isso em uma frase e que dá para pausar ou apagar um no Início."
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
    assumed: dict[str, str] | None = None,
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
        assumed=assumed or None,
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


def reject(offer: PanelOffer) -> None:
    offer.status, offer.decided_at = "rejected", datetime.now(UTC)
