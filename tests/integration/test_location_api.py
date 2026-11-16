"""Somewhere near the owner (docs/LOCALIZACAO.md, ADR-0020): the phone's position goes with a
"near here" question, the map is built in code, the model never sees the coordinates, and
nothing keeps them."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from core import location
from infrastructure.database.models import BrowseVisit, Decision, Message
from integrations.browser.base import Visit
from tests.integration.test_browse_api import (  # noqa: F401 - offline is an autouse fixture
    _actions,
    _chat_prompt,
    _plans,
    offline,
    world,
)
from tests.integration.test_curiosity_api import _login

# A public spot (Avenida Paulista), not anyone's home.
HERE = {"lat": -23.561414, "lon": -46.655881, "accuracy_m": 35}
MAP = location.maps_url("farmácia", location.Here(-23.561414, -46.655881, 35))
PAGE = Visit(
    url=MAP,
    ok=True,
    final_url=MAP.replace("?hl=pt-BR", "/data=!3m1!4b1!3d-23.5614!4d-46.6558?hl=pt-BR"),
    title="farmácia - Google Maps",
    text="Drogasil\n4,1(44)\nFarmácia · Av. Paulista, 2064\nAberto · Fecha 22:00",
)
ASK = "tem farmácia aberta aqui perto?"


def _send(client, headers, text, where=None):
    conversation = client.post("/conversations", headers=headers).json()["id"]
    body = {"content": text, **({"location": where} if where else {})}
    turn = client.post(f"/conversations/{conversation}/messages", headers=headers, json=body)
    assert turn.status_code == 200, turn.text
    return turn.json()


def _everything_kept(db) -> str:
    kept = [m.content for m in db.query(Message).all()]
    kept += [json.dumps(d.actions) for d in db.query(Decision).all()]
    kept += [f"{v.url} {v.title} {v.text}" for v in db.query(BrowseVisit).all()]
    return "\n".join(kept)


def test_near_here_opens_the_map_where_the_owner_is_without_showing_or_keeping_it(client, db):
    llm, browser = world(
        client, db, plan={"browse": True, "nearby": ["farmácia"]}, pages={MAP: PAGE}
    )
    headers = _login(client, db)

    _send(client, headers, ASK, HERE)

    assert browser.opened == [MAP]
    plan_payload = _plans(llm)[0]
    assert plan_payload["perto_dela"] is True
    # The coordinates never reach the model: not the planner, not the reply.
    for prompt in llm.prompts:
        assert all("-23.56" not in m.content and "-46.65" not in m.content for m in prompt)
    system = _chat_prompt(llm)[0].content
    assert "perto dela" in system and "Nunca diga coordenadas" in system
    assert "Drogasil" in _chat_prompt(llm)[-1].content or "Drogasil" in system
    # Nothing kept has them: the map address is stored without the position.
    kept = _everything_kept(db)
    assert "-23.56" not in kept and "-46.65" not in kept
    assert "/@local" in db.query(BrowseVisit).one().url
    used = next(a for a in _actions(db) if a["action"] == "location_used")
    assert used["executed"] is True and used["accuracy"] == "precisão boa (até 100 m)"


def test_a_position_with_a_question_not_about_nearby_is_ignored(client, db):
    llm, browser = world(client, db, plan={"browse": False}, pages={})
    headers = _login(client, db)
    _send(client, headers, "me conta uma curiosidade sobre polvos", HERE)
    assert browser.opened == []
    assert all(a["action"] not in ("location_used", "location_missing") for a in _actions(db))
    assert all(p[0].content != location.MISSING_BLOCK for p in llm.prompts)


def test_near_here_without_a_position_asks_for_the_neighborhood(client, db):
    llm, browser = world(client, db, plan={"browse": False, "missing": ["local"]}, pages={})
    headers = _login(client, db)
    _send(client, headers, ASK)
    assert browser.opened == []
    assert "Usar minha localização" in _chat_prompt(llm)[0].content
    assert any(a["action"] == "location_missing" for a in _actions(db))


@pytest.mark.parametrize(
    ("text", "near"),
    [
        ("tem farmácia aberta aqui perto?", True),
        ("qual o posto mais perto?", True),
        ("algum restaurante bom por aqui?", True),
        ("onde tem caixa eletrônico perto de mim", True),
        ("tem padaria perto?", True),
        ("estou perto de terminar o projeto", False),
        ("já está perto do Natal", False),
        ("daqui a pouco te respondo", False),
        ("aqui está o link que te falei", False),
    ],
)
def test_what_counts_as_near_here(text, near):
    assert location.asks_nearby(text) is near


def test_an_old_or_coarse_position_is_not_here():
    now = datetime(2026, 11, 16, 20, 0, tzinfo=UTC)
    assert location.parse(-23.5, -46.6, 50, now - timedelta(minutes=5), now) is not None
    assert location.parse(-23.5, -46.6, 50, now - timedelta(hours=2), now) is None
    assert location.parse(-23.5, -46.6, 9000, None, now) is None
    assert location.parse(123, -46.6) is None


def test_the_map_address_kept_has_no_position():
    assert location.scrub(PAGE.final_url) == (
        "https://www.google.com/maps/search/farm%C3%A1cia/@local?hl=pt-BR"
    )
    assert location.scrub("https://www.booking.com/@x") == "https://www.booking.com/@x"
