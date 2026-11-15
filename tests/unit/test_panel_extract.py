"""Prices out of recorded pages, checked in code (core/panels/extract.py, ADR-0012). No network:
the pages are text recorded in tests/fixtures/panels, in the shape Google Voos and Google Hotéis
show; the model is a fake that answers what a model could answer, including made-up numbers."""

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from core.panels import urls
from core.panels.extract import Page, check, extract, numbers_in
from core.panels.model import Item, Snapshot, Spec, goal_gap, total
from infrastructure.database.models import ModelUsage
from tests.fakes import FakeLLMProvider

FIXTURES = Path(__file__).parent.parent / "fixtures" / "panels"
READ = datetime(2026, 11, 15, 13, 14, tzinfo=UTC)
FLIGHT_PAGE = Page(
    visit_id=uuid.uuid4(),
    url="https://www.google.com/travel/flights?q=x",
    title="CNF a SCL | Google Voos",
    text=(FIXTURES / "google_flights_cnf_scl.txt").read_text(),
    read_at=READ,
)
HOTEL_PAGE = Page(
    visit_id=uuid.uuid4(),
    url="https://www.google.com/travel/search?q=y",
    title="Hostels em Providencia | Google Hotéis",
    text=(FIXTURES / "google_hotels_providencia.txt").read_text(),
    read_at=READ,
)
SPEC = Spec(
    origin="Belo Horizonte",
    origin_code="CNF",
    destination="Santiago",
    destination_code="SCL",
    depart=date(2027, 8, 14),
    back=date(2027, 8, 21),
    travelers=2,
    hotel_area="Providencia",
    preferences=["hostel"],
    goal=Decimal("6000"),
)


def flight(**changes):
    return {
        "kind": "flight",
        "provider": "LATAM",
        "where": "CNF → SCL",
        "dates": "14–21 ago",
        "connections": 1,
        "price": 4390,
        "price_basis": "total",
        "visit_id": str(FLIGHT_PAGE.visit_id),
        **changes,
    }


def hotel(**changes):
    return {
        "kind": "hotel",
        "provider": "Hostal Providencia",
        "where": "Av. Providencia 2133",
        "dates": "14–21 ago",
        "price": 1555,
        "visit_id": str(HOTEL_PAGE.visit_id),
        **changes,
    }


def test_numbers_are_read_the_way_brazilian_pages_write_them():
    found = numbers_in("R$ 4.390 ida e volta · R$ 1.555,50 · 4,4 (1.203)")
    assert {Decimal("4390"), Decimal("1555.5"), Decimal("1203")} <= found


def test_items_that_the_pages_show_are_kept_with_site_and_time():
    items, rejected = check([flight(), hotel()], [FLIGHT_PAGE, HOTEL_PAGE])
    assert rejected == 0
    assert [i.price for i in items] == [Decimal("4390"), Decimal("1555")]
    assert items[0].site == "google.com" and items[0].read_at == READ


def test_a_price_not_on_the_page_is_cleared_never_kept():
    items, rejected = check([flight(price=3990)], [FLIGHT_PAGE])
    assert rejected == 1 and items[0].price is None  # "a confirmar", not a made-up number


def test_an_item_from_a_page_that_was_not_read_is_dropped():
    items, rejected = check([flight(visit_id=str(uuid.uuid4()))], [FLIGHT_PAGE])
    assert items == [] and rejected == 1


def test_a_hotel_price_cannot_come_from_the_flight_page():
    items, _ = check([hotel(price=4390)], [FLIGHT_PAGE, HOTEL_PAGE])
    assert items[0].price is None


def test_the_total_and_the_goal_are_computed_in_code():
    items, _ = check([flight(), hotel()], [FLIGHT_PAGE, HOTEL_PAGE])
    snap = Snapshot(items=items, checked_at=READ)
    assert total(snap, SPEC) == Decimal("5945.00")
    assert goal_gap(total(snap, SPEC), SPEC) == Decimal("-55.00")  # R$ 55 below the goal


def test_a_price_per_person_counts_for_the_whole_party():
    item = Item(**flight(price=2195, price_basis="per_person"))
    assert item.cost(2) == Decimal("4390")


def test_without_every_price_the_total_is_to_be_confirmed():
    items, _ = check([flight(price=None), hotel()], [FLIGHT_PAGE, HOTEL_PAGE])
    assert total(Snapshot(items=items, checked_at=READ), SPEC) is None
    only_flight, _ = check([flight()], [FLIGHT_PAGE])
    assert total(Snapshot(items=only_flight, checked_at=READ), SPEC) is None  # no stay yet


def test_the_extraction_call_goes_through_the_provider_and_is_recorded(db: Session):
    answer = {"spec": SPEC.model_dump(mode="json"), "items": [flight(), hotel(price=999)]}
    llm = FakeLLMProvider(responder=lambda _m: json.dumps(answer))
    found = extract(db, llm, [FLIGHT_PAGE, HOTEL_PAGE], today=date(2026, 11, 15))
    assert found is not None and found.spec is not None and found.spec.destination == "Santiago"
    assert [i.price for i in found.items] == [Decimal("4390"), None]
    assert found.rejected == 1
    assert db.query(ModelUsage).one().purpose == "panel_extract"


def test_when_the_call_fails_nothing_is_made_up(db: Session):
    llm = FakeLLMProvider(fail_with="budget_denied")
    assert extract(db, llm, [FLIGHT_PAGE], today=date(2026, 11, 15)) is None


@pytest.mark.parametrize("bad", ["não sei", '{"items": "x"}', '{"items": [{"kind": "train"}]}'])
def test_bad_answers_give_no_items(db: Session, bad):
    llm = FakeLLMProvider(responder=lambda _m: bad)
    found = extract(db, llm, [FLIGHT_PAGE], today=date(2026, 11, 15), spec=SPEC)
    assert found is not None and found.items == []


def test_the_daily_pages_come_from_the_spec():
    built = urls.for_spec(SPEC, max_pages=2)
    assert built[0].startswith("https://www.google.com/travel/flights?q=Flights%20to%20SCL")
    assert "2027-08-14%20through%202027-08-21" in built[0] and "for%202%20adults" in built[0]
    assert "hostels%20em%20Providencia%20Santiago" in built[1]
    assert urls.for_spec(Spec(destination="Santiago"), 2) == []  # no dates: nothing to open


def test_a_panel_expires_after_the_trip():
    assert SPEC.ended(date(2027, 8, 22)) and not SPEC.ended(date(2027, 8, 20))
