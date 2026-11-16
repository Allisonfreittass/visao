"""A live quote ends with a table of options (docs/decisions/0015, docs/COTACAO_TABELA.md): the
data for the apps that know it, its text as the last bubble for the ones that do not, and the
assumptions carried into the panel offer."""

import json

from apps.api.browser import get_browser
from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core import browse
from core.identity.genesis import run_genesis
from core.panels.extract import INSTRUCTIONS as EXTRACT_INSTRUCTIONS
from infrastructure.database.models import Panel, PanelOffer
from integrations.browser.base import Visit
from tests.fakes import FakeLLMProvider
from tests.integration.test_browse_api import (  # noqa: F401 - offline is an autouse fixture
    FakeBrowser,
    _chat_prompt,
    _send,
    offline,
)
from tests.integration.test_curiosity_api import _login

FLIGHTS = "https://www.google.com/travel/flights?q=GRU-SCL"
HOTELS = "https://www.google.com/travel/search?q=hoteis-santiago"
ASSUMED = {"origem": "Guarulhos (GRU), saindo do sul de Minas", "pessoas": "2 adultos"}
REPLY = "Considerei saída de Guarulhos, para dois. O combo mais barato está abaixo. Quer ajustar?"


def quote_world(client, db, *, extracted=True):
    pages = {
        FLIGHTS: Visit(
            url=FLIGHTS,
            ok=True,
            final_url=FLIGHTS,
            title="Voos GRU-SCL",
            text="JetSMART R$ 1.200 por pessoa, não inclui bagagem de mão. LATAM R$ 1.800",
        ),
        HOTELS: Visit(
            url=HOTELS, ok=True, final_url=HOTELS, title="Hotéis", text="Hostel Providencia R$ 900"
        ),
    }

    def respond(messages):
        system = messages[0].content
        if system == browse.INSTRUCTIONS:
            return json.dumps(
                {
                    "browse": True,
                    "urls": [FLIGHTS, HOTELS],
                    "assumed": ASSUMED,
                    "title": "Combo Santiago",
                }
            )
        if system == EXTRACT_INSTRUCTIONS:
            if not extracted:
                return "não sei"
            ids = {p["url"]: p["visit_id"] for p in json.loads(messages[1].content)["pages"]}
            return json.dumps(
                {
                    "spec": {"destination": "Santiago", "travelers": 2},
                    "items": [
                        {
                            "kind": "flight",
                            "provider": "JetSMART",
                            "price": 1200,
                            "price_basis": "per_person",
                            "visit_id": ids[FLIGHTS],
                            "not_included": "bagagem de mão",
                        },
                        {
                            "kind": "flight",
                            "provider": "LATAM",
                            "price": 1800,
                            "price_basis": "per_person",
                            "visit_id": ids[FLIGHTS],
                        },
                        {
                            "kind": "hotel",
                            "provider": "Hostel Providencia",
                            "price": 900,
                            "visit_id": ids[HOTELS],
                        },
                    ],
                }
            )
        if "A pessoa aceitou o painel" in system:
            return "Pronto, está no Início."
        return REPLY

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_browser] = lambda: FakeBrowser(pages)
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm


def test_the_quote_comes_with_a_table_and_its_text_as_the_last_bubble(client, db):
    llm = quote_world(client, db)
    headers = _login(client, db)

    conversation, turn = _send(client, headers, "quanto tá a passagem pra Santiago em agosto?")

    message = turn["assistant_message"]
    table = message["quote_table"]
    assert [r["option"] for r in table["rows"]] == [
        "JetSMART + Hostel Providencia",
        "LATAM + Hostel Providencia",
    ]
    assert table["rows"][0]["total_text"] == "R$ 3.300"
    assert "Fica de fora do total: bagagem de mão (JetSMART)." in table["notes"]
    # An app that does not know quote_table shows the same thing as text, in its own bubble.
    assert message["parts"] == [REPLY, table["text"]]
    assert message["content"].endswith(table["text"])
    # The reply was told the table goes below it, and never to offer to book.
    system = _chat_prompt(llm)[0].content
    assert "Abaixo da sua resposta vai uma tabela" in system and "nunca ofereça reservar" in system
    # Read again later, the table is still there.
    listed = client.get(f"/conversations/{conversation}/messages", headers=headers).json()
    assert listed[-1]["quote_table"] == table


def test_the_panel_made_from_the_quote_shows_what_was_assumed(client, db):
    quote_world(client, db)
    headers = _login(client, db)
    conversation, _ = _send(client, headers, "quanto tá a passagem pra Santiago em agosto?")
    assert db.query(PanelOffer).one().assumed == ASSUMED

    _send(client, headers, "por favor", conversation)

    assert db.query(Panel).one().spec["assumed"] == ASSUMED


def test_without_checked_prices_there_is_no_table(client, db):
    quote_world(client, db, extracted=False)
    headers = _login(client, db)
    _, turn = _send(client, headers, "quanto tá a passagem pra Santiago em agosto?")
    message = turn["assistant_message"]
    assert message["quote_table"] is None and message["content"] == REPLY


def test_a_voice_turn_reads_no_table(client, db):
    quote_world(client, db)
    headers = _login(client, db)
    conversation = client.post("/conversations", headers=headers).json()["id"]
    turn = client.post(
        f"/conversations/{conversation}/messages",
        headers=headers,
        json={"content": "quanto tá a passagem pra Santiago em agosto?", "modality": "voice"},
    ).json()
    assert turn["assistant_message"]["quote_table"] is None
