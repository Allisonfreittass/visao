"""A package with one item priced shows a partial, what is missing and what is left of the goal:
the price of one item is never the package's total."""

from datetime import UTC, datetime
from decimal import Decimal

from core.panels import service as panels
from core.panels.model import Item, Snapshot, Spec, missing, partial, total

SANTIAGO = Spec(destination="Santiago", travelers=2, goal=Decimal("4000"))


def hotel(price: str | None) -> Item:
    return Item(
        kind="hotel", provider="Hotel Providencia", price=price and Decimal(price), visit_id="v1"
    )


def flight(price: str | None, basis: str = "per_person") -> Item:
    return Item(
        kind="flight",
        provider="LATAM",
        price=price and Decimal(price),
        price_basis=basis,
        visit_id="v2",
    )


def snap(*items: Item) -> Snapshot:
    return Snapshot(items=list(items), checked_at=datetime.now(UTC))


def test_only_the_hotel_priced_is_a_partial_not_a_total():
    shot = snap(hotel("1640"))
    assert total(shot, SANTIAGO) is None
    assert partial(shot, SANTIAGO) == Decimal("1640.00")
    assert missing(shot, SANTIAGO) == ["flight"]
    line = panels.goal_line(None, SANTIAGO.goal, None, partial(shot, SANTIAGO), ["flight"])
    assert line == "parcial de R$ 1.640 na meta de R$ 4.000: sobram R$ 2.360 para voo"


def test_an_item_found_without_a_price_is_still_missing():
    shot = snap(hotel("1640"), flight(None))
    assert missing(shot, SANTIAGO) == ["flight"]
    assert partial(shot, SANTIAGO) == Decimal("1640.00")


def test_a_partial_over_the_goal_says_so_and_what_is_left_to_quote():
    line = panels.goal_line(None, Decimal("1000"), None, Decimal("1640"), ["flight"])
    assert line == "parcial de R$ 1.640 já passa a meta de R$ 1.000 em R$ 640, e ainda falta voo"


def test_with_everything_priced_it_is_the_total_as_before():
    shot = snap(hotel("1640"), flight("900"))
    value = total(shot, SANTIAGO)
    assert value == Decimal("3440.00")  # 900 per person, two travelers
    assert missing(shot, SANTIAGO) == []
    line = panels.goal_line(value, SANTIAGO.goal, value - SANTIAGO.goal, None, [])
    assert line == "R$ 560 abaixo da meta de R$ 4.000"
