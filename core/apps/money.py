"""Tools that move money, through the owner's apps (docs/APPS.md, "Pagamentos").

Composio lists payment apps too (Stripe, PayPal, Square…). Their "send a payout" or "refund a
charge" were plain writes: a card with Aprovar like renaming an issue, with no amount shown and no
limit. Here they are told apart and held to stricter rules:

- **Off by default.** A money tool is never offered to the model, in any app, unless the owner
  turned on "Pagamentos" for that app in Ajustes, with a daily ceiling.
- **Only from the owner's own words.** Never for content shared from another app, never from the
  mind or a glance (those never propose anything).
- **The amount, or nothing.** A payment whose amount cannot be read from its arguments is not
  prepared: the card always says how much, in what currency and to whom.
- **At approval:** a tap only (never a "sim" said in a call), the amount confirmed by the owner,
  the switch still on, the currency the ceiling's, and the day's total within the ceiling.

Telling them apart is by words, in the tool and in the app: Composio's hints say whether a tool
writes, not whether it pays. "transfer" alone is not money (GitHub transfers repositories); it is
in a payment app.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.memory.text import fold
from infrastructure.database.models import ToolAction, User

KEY = "apps_payments"  # in User.autonomy_permissions: {toolkit: {"cap": "200.00", "currency"}}
DEFAULT_CURRENCY = "BRL"
MAX_CAP = Decimal("100000")

# Apps whose writes are about money: here any charge, transfer or invoice counts.
PAYMENT_APPS = frozenset({
    "stripe", "paypal", "square", "mercadopago", "mercado_pago", "pagseguro", "asaas", "wise",
    "revolut", "razorpay", "braintree", "adyen", "checkout", "paddle", "lemonsqueezy", "gumroad",
    "chargebee", "recurly", "plaid", "brex", "ramp", "mercury", "coinbase", "venmo", "zelle",
})  # fmt: skip
# Words that are money in any app.
_STRONG = re.compile(
    r"\b(?:payments?|payouts?|pay out|refunds?|money|disburse\w*|withdraw\w*|remittance|"
    r"pix|boleto|pagamentos?|pagar|estorn\w*|saques?|sacar|transferencia bancaria|wire)\b"
)
# Words that are money in a payment app.
_IN_PAYMENT_APP = re.compile(
    r"\b(?:charges?|transfers?|invoices?|capture|send|subscriptions?|checkout|cobra\w*|"
    r"fatura\w*|transferir|assinatura\w*)\b"
)
_AMOUNT_KEYS = ("amount", "value", "valor", "unit_amount", "total", "price", "amount_cents")
_CURRENCY_KEYS = ("currency", "currency_code", "moeda")
_TO_KEYS = (
    "recipient", "to", "destination", "receiver", "payee", "customer", "email",
    "receiver_email", "account", "beneficiary", "destinatario",
)  # fmt: skip
# Apps that take amounts in minor units (cents) as integers.
_MINOR_UNITS = frozenset({"stripe", "square", "adyen", "checkout", "paddle"})


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str
    to: str

    def words(self) -> str:
        shown = f"{self.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{self.currency} {shown}" + (f" para {self.to}" if self.to else "")


def _text(slug: str, name: str, description: str) -> str:
    return fold(f"{slug.replace('_', ' ')} {name} {description}")


def is_money(toolkit: str, slug: str, name: str = "", description: str = "") -> bool:
    text = _text(slug, name, description)
    if _STRONG.search(text):
        return True
    return toolkit.lower() in PAYMENT_APPS and bool(_IN_PAYMENT_APP.search(text))


def payment_app(toolkit: str, categories: tuple[str, ...] = ()) -> bool:
    """Whether the Pagamentos switch is worth showing for this app."""
    cats = fold(" ".join(categories))
    return toolkit.lower() in PAYMENT_APPS or any(
        w in cats for w in ("payment", "finance", "accounting", "ecommerce", "banking")
    )


def _walk(data: Any, keys: tuple[str, ...], depth: int = 0) -> tuple[str, Any] | None:
    if depth > 4 or not isinstance(data, dict):
        return None
    for key, value in data.items():
        if str(key).lower() in keys and not isinstance(value, dict | list):
            return str(key).lower(), value
    for value in data.values():
        found = _walk(value, keys, depth + 1)
        if found is not None:
            return found
    return None


def read(toolkit: str, arguments: dict[str, Any]) -> Money | None:
    """The amount, currency and recipient a payment's arguments carry; None without an amount."""
    found = _walk(arguments, _AMOUNT_KEYS)
    if found is None or isinstance(found[1], bool):
        return None
    key, raw = found
    try:
        amount = Decimal(repr(raw) if isinstance(raw, float) else str(raw).replace(",", "."))
    except InvalidOperation:
        return None
    if isinstance(raw, int) and ("cent" in key or toolkit.lower() in _MINOR_UNITS):
        amount = amount / 100
    if not amount.is_finite() or amount <= 0:
        return None
    currency = _walk(arguments, _CURRENCY_KEYS)
    to = _walk(arguments, _TO_KEYS)
    return Money(
        amount=amount.quantize(Decimal("0.01")),
        currency=str(currency[1]).upper()[:6] if currency else "",
        to=str(to[1])[:120] if to else "",
    )


def allowed(owner: User) -> dict[str, dict[str, str]]:
    value = (owner.autonomy_permissions or {}).get(KEY)
    return dict(value) if isinstance(value, dict) else {}


def set_allowed(owner: User, toolkit: str, cap: Decimal | None, currency: str = "") -> None:
    """cap None turns payments off for the app."""
    current = allowed(owner)
    if cap is None:
        current.pop(toolkit, None)
    else:
        current[toolkit] = {
            "cap": str(cap.quantize(Decimal("0.01"))),
            "currency": (currency or DEFAULT_CURRENCY).upper()[:6],
        }
    owner.autonomy_permissions = {**(owner.autonomy_permissions or {}), KEY: current}


def _day_start(owner: User, now: datetime) -> datetime:
    try:
        zone = ZoneInfo(owner.timezone or "UTC")
    except Exception:  # noqa: BLE001 (an unknown zone counts the UTC day)
        zone = ZoneInfo("UTC")
    local = now.astimezone(zone)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def spent_today(
    session: Session, owner: User, toolkit: str, now: datetime, *, besides: uuid.UUID | None = None
) -> Decimal:
    """The payments of the owner's day in this app that ran, or are running; `besides`: the one
    being approved, which is already claimed."""
    rows = session.scalars(
        select(ToolAction).where(
            ToolAction.owner_user_id == owner.id,
            ToolAction.toolkit == toolkit,
            ToolAction.id != besides if besides else True,
            ToolAction.status.in_(("done", "running", "approved")),
            ToolAction.created_at >= _day_start(owner, now) - timedelta(days=1),
        )
    )
    total = Decimal("0")
    start = _day_start(owner, now)
    for row in rows:
        money = (row.payload or {}).get("money")
        decided = row.decided_at or row.created_at
        if money and decided and _utc(decided) >= start:
            total += Decimal(str(money.get("amount") or "0"))
    return total


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def refusal_at_approval(
    session: Session,
    owner: User,
    action: ToolAction,
    *,
    via: str,
    confirmed: str | None,
    now: datetime,
) -> str | None:
    """Why a payment cannot run now, in the owner's words; None when it can."""
    money = (action.payload or {}).get("money")
    if not money:
        return None
    if via != "toque":
        return "Pagamento só sai com um toque no cartão, não pela voz."
    rule = allowed(owner).get(action.toolkit)
    if not rule:
        return "Os pagamentos desse app estão desligados em Ajustes; não fiz."
    amount = Decimal(str(money.get("amount")))
    if confirmed is None or not _same(confirmed, amount):
        return "O valor confirmado não bate com o do pedido; não fiz."
    if money.get("currency") and money["currency"] != rule.get("currency"):
        return (
            f"O teto está em {rule.get('currency')} e o pagamento é em {money['currency']}; "
            "não fiz."
        )
    cap = Decimal(str(rule.get("cap") or "0"))
    already = spent_today(session, owner, action.toolkit, now, besides=action.id)
    if already + amount > cap:
        return (
            f"Passaria do teto de hoje ({rule.get('currency')} {cap}; já foram {already}); não fiz."
        )
    return None


def _same(confirmed: str, amount: Decimal) -> bool:
    try:
        return Decimal(str(confirmed).replace(",", ".")).quantize(Decimal("0.01")) == amount
    except InvalidOperation:
        return False
