"""A quote with declared assumptions instead of a reply that stops to ask (docs/decisions/0015).
The origin comes from where the owner lives, in their own words kept with consent, and its
airports from a table in code; the reply opens saying what was assumed."""

import json

import pytest
from sqlalchemy import select

from core import browse
from core.mind import notes as mind_notes
from core.travel_origins import _found
from infrastructure.database.models import User
from integrations.browser.base import Visit
from tests.integration.test_browse_api import (  # noqa: F401 - offline is an autouse fixture
    _actions,
    _chat_prompt,
    _plans,
    _send,
    offline,
    world,
)
from tests.integration.test_curiosity_api import _login

GRU = (
    "https://www.google.com/travel/flights?q=Flights%20to%20SCL%20from%20GRU%20on%202027-08-14"
    "%20through%202027-08-24&hl=pt-BR&curr=BRL"
)
ASSUMED = {
    "origem": "Guarulhos (GRU), saindo do sul de Minas",
    "datas": "14 a 24/08/2027",
    "pessoas": "2 adultos",
}


def _lives_in(db, where: str) -> None:
    owner = db.scalar(select(User))
    owner.memory_consent = True
    mind_notes.write(db, owner.id, mind_notes.PROFILE, where, "teste")
    db.commit()


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Mora em Pouso Alegre, no sul de Minas, com a esposa.", "sul de Minas"),
        ("Allison mora em Belo Horizonte.", "Belo Horizonte"),
        ("Sou de Campinas e trabalho com tecnologia.", "Campinas"),
        ("Vai viajar para São Paulo em dezembro.", None),
        ("Gosta de café e de esquiar.", None),
    ],
)
def test_where_the_owner_lives_comes_only_from_their_own_words(text, label):
    found = _found(text)
    assert (found.label if found else None) == label


def test_the_planner_gets_the_airports_from_where_the_owner_lives(client, db):
    page = Visit(url=GRU, ok=True, final_url=GRU, title="GRU a SCL", text="LATAM R$ 2.019")
    plan = {"browse": True, "urls": [GRU], "assumed": ASSUMED, "title": "Santiago em agosto"}
    llm, browser = world(client, db, plan=plan, pages={GRU: page})
    headers = _login(client, db)
    _lives_in(db, "Mora em Pouso Alegre, no sul de Minas.")

    _send(client, headers, "quero ver passagem pra Santiago em agosto, 10 dias lá")

    assert _plans(llm)[0]["home"] == {
        "onde_mora": "sul de Minas",
        "aeroportos": ["GRU", "VCP", "CNF"],
    }
    browsed = next(a for a in _actions(db) if a["action"] == "browsed")
    assert browsed["assumed"] == ASSUMED
    system = _chat_prompt(llm)[0].content
    assert "Esta cotação usou suposições" in system and "origem: Guarulhos (GRU)" in system


def test_without_consent_where_the_owner_lives_is_not_read(client, db):
    llm, _ = world(client, db, plan={"browse": False, "missing": ["origem"]}, pages={})
    headers = _login(client, db)
    _lives_in(db, "Mora em Pouso Alegre.")
    owner = db.scalar(select(User))
    owner.memory_consent = False
    db.commit()

    _send(client, headers, "quero ver passagem pra Santiago em agosto, 10 dias lá")

    assert _plans(llm)[0]["home"] is None


def test_without_a_known_city_it_asks_only_the_origin(client, db):
    llm, browser = world(client, db, plan={"browse": False, "missing": ["origem"]}, pages={})
    headers = _login(client, db)

    _send(client, headers, "quero ver passagem pra Santiago em agosto, 10 dias lá")

    assert _plans(llm)[0]["home"] is None and browser.opened == []
    system = _chat_prompt(llm)[0].content
    assert "para buscar falta: origem." in system


def test_nothing_assumed_adds_no_assumption_line(client, db):
    page = Visit(url=GRU, ok=True, final_url=GRU, title="GRU a SCL", text="LATAM R$ 2.019")
    llm, _ = world(client, db, plan={"browse": True, "urls": [GRU]}, pages={GRU: page})
    headers = _login(client, db)
    _send(client, headers, "quanto tá a passagem de GRU pra Santiago de 14 a 24/08?")
    assert "Esta cotação usou suposições" not in _chat_prompt(llm)[0].content


def test_the_planner_knows_the_three_messages_of_16_11():
    for said in (
        "Estou querendo ir em agosto e ficar 10 dias lá",
        "Eu quero esquiar sim e acho melhor ficar em Santiago mesmo, o que acha?",
        "o preço sobe muito se eu pegar aulas?",
    ):
        assert said in browse.INSTRUCTIONS
    assert "Nunca reserve ou compre" in browse.INSTRUCTIONS
    assert json.loads(json.dumps(ASSUMED)) == browse._assumed({"assumed": ASSUMED})
