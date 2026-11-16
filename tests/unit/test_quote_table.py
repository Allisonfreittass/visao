"""The table of options under a live quote, built in code from checked items (ADR-0015)."""

from datetime import date
from decimal import Decimal

from core.panels import quote
from core.panels.extract import Page, check
from core.panels.model import Item, Spec
from core.travel_origins import Home

SPEC = Spec(destination="Santiago", depart=date(2027, 8, 14), back=date(2027, 8, 24), travelers=2)
HOME = Home("sul de Minas", ("GRU", "VCP", "CNF"))


def item(kind, provider, price, dates="14–24 ago", basis="per_person", site="google.com", **more):
    return Item(
        kind=kind,
        provider=provider,
        price=Decimal(price) if price is not None else None,
        price_basis=basis,
        dates=dates,
        site=site,
        visit_id="v",
        **more,
    )


def test_combos_are_summed_for_the_party_and_ordered_from_the_cheapest():
    items = [
        item("flight", "LATAM", "1800"),
        item("flight", "JetSMART", "1200", not_included="bagagem de mão"),
        item("hotel", "Hostel Providencia", "900", basis="total"),
        item("hotel", "Hotel Plaza", "2500", basis="total"),
    ]
    table = quote.build(items, SPEC, hint="Combo Santiago", assumed={}, home=None)

    assert table["title"] == "Santiago, 10 noites em agosto de 2027"
    assert table["travelers"] == 2
    assert [r["option"] for r in table["rows"]] == [
        "JetSMART + Hostel Providencia",
        "LATAM + Hostel Providencia",
        "JetSMART + Hotel Plaza",
        "LATAM + Hotel Plaza",
    ]
    assert table["rows"][0]["total"] == "3300.00"  # 1200 × 2 + 900
    assert table["rows"][0]["total_text"] == "R$ 3.300"
    assert table["notes"] == ["Fica de fora do total: bagagem de mão (JetSMART)."]
    first_line = table["text"].splitlines()[1]
    assert first_line == "1. JetSMART + Hostel Providencia · 14–24 ago · R$ 3.300"


def test_at_most_five_rows_and_never_one_without_a_price():
    flights = [item("flight", f"Cia {n}", str(1000 + n)) for n in range(4)]
    stays = [item("hotel", f"Hotel {n}", str(500 + n), basis="total") for n in range(3)]
    unpriced = item("hotel", "Sem preço", None, basis="total")
    table = quote.build([*flights, *stays, unpriced], SPEC)
    assert len(table["rows"]) == quote.MAX_ROWS
    assert all("Sem preço" not in r["option"] for r in table["rows"])
    assert quote.build([unpriced], SPEC) is None


def test_a_clearly_cheaper_window_earns_one_sentence():
    items = [
        item("flight", "LATAM", "2000", dates="03–13 ago"),
        item("flight", "LATAM", "1700", dates="14–24 ago"),
    ]
    assert quote.neighbor_sentence(items, 2) == "Saindo em 14–24 ago, o voo cai para R$ 3.400."
    close = [item("flight", "A", "2000", dates="03–13 ago"), item("flight", "B", "1950")]
    assert quote.neighbor_sentence(close, 2) == ""


def test_the_trip_to_an_assumed_airport_is_said_to_be_left_out():
    sentence = quote.costs_sentence(
        [item("flight", "LATAM", "1800")],
        {"origem": "Guarulhos (GRU), saindo do sul de Minas"},
        HOME,
    )
    assert sentence == "Fica de fora do total: o deslocamento do sul de Minas até GRU."
    assert quote.costs_sentence([item("flight", "LATAM", "1800")], {}, HOME) == ""


def test_the_party_comes_from_the_conversation_or_what_was_assumed():
    assert quote.travelers(Spec(destination="X", travelers=3), {}) == 3
    assert quote.travelers(Spec(destination="X"), {"pessoas": "2 adultos"}) == 2
    assert quote.travelers(None, {}) == 2


def test_a_left_out_cost_is_kept_only_when_the_page_says_it():
    from datetime import UTC, datetime

    page = Page(
        visit_id="11111111-1111-1111-1111-111111111111",
        url="https://www.google.com/travel/flights",
        title="Voos",
        text="JetSMART R$ 1.200 · tarifa Light, não inclui bagagem de mão",
        read_at=datetime.now(UTC),
    )
    raw = {
        "kind": "flight",
        "provider": "JetSMART",
        "price": 1200,
        "visit_id": str(page.visit_id),
    }
    kept, _ = check([{**raw, "not_included": "bagagem de mão"}], [page])
    assert kept[0].not_included == "bagagem de mão"
    invented, rejected = check([{**raw, "not_included": "taxa de embarque"}], [page])
    assert invented[0].not_included == "" and rejected == 1
