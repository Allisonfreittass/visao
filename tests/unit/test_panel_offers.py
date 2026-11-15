"""The panel offer's rules in code (core/panels/offers.py): the owner's budget read from their
words, a plain yes, and prices seen in the pages read live."""

from decimal import Decimal

import pytest

from core.panels.offers import affirmative, goal_from, has_prices, money


@pytest.mark.parametrize(
    ("text", "goal"),
    [
        ("quero gastar até R$ 6 mil", Decimal("6000")),
        ("orçamento de 6.000 reais pra dois", Decimal("6000")),
        ("muda a meta pra R$ 5.500", Decimal("5500")),
        ("no máximo R$ 4.250,50", Decimal("4250.50")),
        ("até 8k", Decimal("8000")),
    ],
)
def test_the_budget_comes_from_the_owners_words(text, goal):
    assert goal_from(text) == goal


@pytest.mark.parametrize("text", ["até agosto", "até 2027", "fico até 10 dias", "a dois"])
def test_without_money_in_sight_there_is_no_budget(text):
    assert goal_from(text) is None


def test_the_latest_budget_wins():
    assert goal_from("até R$ 6 mil", "melhor até R$ 5 mil") == Decimal("5000")


def test_money_is_written_the_brazilian_way():
    assert money(Decimal("6000")) == "R$ 6.000"
    assert money(Decimal("4250.5")) == "R$ 4.250,50"


@pytest.mark.parametrize(
    "text", ["por favor", "Pode!", "quero sim", "sim, por favor", "bora", "pode fazer"]
)
def test_a_plain_yes_accepts(text):
    assert affirmative(text)


@pytest.mark.parametrize(
    "text",
    ["não, obrigado", "agora não", "pode ser que eu vá em setembro", "quero ver hotéis também", ""],
)
def test_anything_else_does_not(text):
    assert not affirmative(text)


def test_prices_in_the_pages():
    assert has_prices(["LATAM · 1 parada · R$ 2.195"])
    assert not has_prices(["Santiago é a capital do Chile"])
