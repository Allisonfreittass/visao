"""What a live panel quotes and what it found, as validated data (ADR-0012).

The total and the distance to the goal are computed here, in code, never by the model. A price
that is missing leaves the total "a confirmar"; nothing is ever filled in by guess.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ItemKind = Literal["flight", "hotel"]
PriceBasis = Literal["per_person", "total"]


class Spec(BaseModel):
    """What to quote. `goal` is the owner's own number, read in code (offers.goal_from)."""

    model_config = ConfigDict(extra="ignore")

    origin: str | None = Field(default=None, max_length=60)
    destination: str = Field(min_length=1, max_length=60)
    # IATA codes when known: the flight search needs them.
    origin_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    destination_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    depart: date | None = None
    back: date | None = None
    travelers: int = Field(default=1, ge=1, le=9)
    hotel_area: str | None = Field(default=None, max_length=80)
    preferences: list[str] = Field(default_factory=list, max_length=6)
    include: list[ItemKind] = Field(default_factory=lambda: ["flight", "hotel"], min_length=1)
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    goal: Decimal | None = Field(default=None, ge=0, le=10_000_000)
    # What the quote assumed instead of asking, shown on the card ("considerando saída de GRU").
    assumed: dict[str, str] = Field(default_factory=dict)

    @field_validator("preferences")
    @classmethod
    def _short(cls, items: list[str]) -> list[str]:
        return [" ".join(i.split())[:40] for i in items if i.strip()]

    def ended(self, today: date) -> bool:
        """The trip is over (or started): the panel expires."""
        last = self.back or self.depart
        return last is not None and last < today

    def nights(self) -> int | None:
        if self.depart and self.back and self.back > self.depart:
            return (self.back - self.depart).days
        return None


class Item(BaseModel):
    """One thing quoted (a flight, a stay), as a page showed it."""

    model_config = ConfigDict(extra="ignore")

    kind: ItemKind
    provider: str = Field(min_length=1, max_length=80)
    # The route ("CNF → SCL") or the address/neighborhood of the stay.
    where: str = Field(default="", max_length=120)
    dates: str = Field(default="", max_length=60)
    connections: int | None = Field(default=None, ge=0, le=5)
    price: Decimal | None = Field(default=None, gt=0, le=10_000_000)
    price_basis: PriceBasis = "total"
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    site: str = Field(default="", max_length=80)
    url: str = Field(default="", max_length=600)
    visit_id: str
    read_at: datetime | None = None
    # What the page says the price leaves out ("bagagem de mão"), checked against its text.
    not_included: str = Field(default="", max_length=80)

    def cost(self, travelers: int) -> Decimal | None:
        """What this item costs the whole party."""
        if self.price is None:
            return None
        return self.price * travelers if self.price_basis == "per_person" else self.price


class Snapshot(BaseModel):
    items: list[Item] = Field(default_factory=list, max_length=6)
    checked_at: datetime
    # Shown on the card when the check could not be done in full ("o site pediu verificação").
    note: str = ""


def total(snapshot: Snapshot, spec: Spec) -> Decimal | None:
    """The sum for the party, or None when any wanted item has no price (then: "a confirmar")."""
    if not snapshot.items:
        return None
    present = {i.kind for i in snapshot.items}
    if not set(spec.include) <= present:
        return None
    costs = [i.cost(spec.travelers) for i in snapshot.items]
    if any(c is None for c in costs):
        return None
    return sum(costs, Decimal(0)).quantize(Decimal("0.01"))  # type: ignore[arg-type]


def partial(snapshot: Snapshot, spec: Spec) -> Decimal | None:
    """The sum of the items already priced, for the party; None when none has a price. Never
    the total: a panel with a missing item shows this as "parcial" beside what is missing."""
    costs = [c for c in (i.cost(spec.travelers) for i in snapshot.items) if c is not None]
    return sum(costs, Decimal(0)).quantize(Decimal("0.01")) if costs else None


def missing(snapshot: Snapshot | None, spec: Spec) -> list[ItemKind]:
    """What the quote wants and still has no price: an item not found, or found without one."""
    priced = {i.kind for i in (snapshot.items if snapshot else []) if i.price is not None}
    return [kind for kind in spec.include if kind not in priced]


def goal_gap(value: Decimal | None, spec: Spec) -> Decimal | None:
    """Positive: above the goal by that much; negative: below it. None without a goal or total."""
    if value is None or spec.goal is None:
        return None
    return (value - spec.goal).quantize(Decimal("0.01"))
