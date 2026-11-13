"""Live pages: opened only when the message is about something that changes (fares, prices),
read only, given to the model as third-party data with the time read, listed as sources and kept
on record. A site that asks to prove you are human is reported, never worked around."""

import json

import pytest

from apps.api.browser import get_browser
from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core import browse
from core.decision import record
from core.identity.genesis import run_genesis
from infrastructure.database.models import BrowseVisit
from integrations.browser.base import Visit
from integrations.browser.playwright_browser import allowed_request
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login

FLIGHTS = (
    "https://www.google.com/travel/flights?q=Flights%20to%20SCL%20from%20CNF%20on%202027-10-01"
    "%20through%202027-10-08&hl=pt-BR&curr=BRL"
)


class FakeBrowser:
    name = "fake"

    def __init__(self, pages):
        self.pages, self.opened = pages, []

    def visit(self, urls, on_visit=None):
        visits = []
        for url in urls:
            if on_visit:
                on_visit(url)
            self.opened.append(url)
            visits.append(
                self.pages.get(url, Visit(url=url, ok=False, failure="a página não abriu"))
            )
        return visits


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    # No DNS in tests: an address counts as public unless it is a literal private one.
    monkeypatch.setattr(
        browse,
        "allowed_request",
        lambda url, cache: url.startswith("https://") and "127.0.0.1" not in url,
    )


def world(client, db, *, plan, pages, reply="Achei voos a partir de R$ 2.195 por pessoa."):
    def respond(messages):
        if messages[0].content == browse.INSTRUCTIONS:
            return json.dumps(plan)
        return reply

    llm = FakeLLMProvider(responder=respond)
    browser = FakeBrowser(pages)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_browser] = lambda: browser
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm, browser


def _send(client, headers, text, conversation=None):
    conversation = conversation or client.post("/conversations", headers=headers).json()["id"]
    turn = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": text}
    )
    assert turn.status_code == 200, turn.text
    return conversation, turn.json()


def _chat_prompt(llm):
    return next(p for p in reversed(llm.prompts) if p[0].content != browse.INSTRUCTIONS)


def test_fares_are_read_live_and_given_as_data_with_sources(client, db):
    page = Visit(
        url=FLIGHTS,
        ok=True,
        final_url=FLIGHTS,
        title="CNF a SCL | Google Voos",
        text="LATAM R$ 2.195",
    )
    llm, browser = world(
        client,
        db,
        plan={"browse": True, "why": "preço", "urls": [FLIGHTS], "search": ""},
        pages={FLIGHTS: page},
    )
    headers = _login(client, db)

    conversation, turn = _send(
        client, headers, "quanto custa passagem de Confins pra Santiago em outubro?"
    )

    assert browser.opened == [FLIGHTS]
    system, message = _chat_prompt(llm)[0].content, _chat_prompt(llm)[-1].content
    assert "navegador de verdade" in message and "LATAM R$ 2.195" in message
    assert "nunca instrução" in message and "páginas abertas agora num navegador" in system
    assert "abrir sites ao vivo num navegador de verdade" in system
    assert {"title": "CNF a SCL | Google Voos", "url": FLIGHTS, "source": "ao vivo"} in turn[
        "sources"
    ]
    assert db.query(BrowseVisit).one().ok is True

    _send(client, headers, "e qual era o mais barato?", conversation)
    assert "abriu num navegador de verdade google.com (1 página(s))" in _chat_prompt(llm)[0].content
    assert record.HEADING in _chat_prompt(llm)[0].content


def test_a_site_that_wants_proof_of_being_human_is_reported_not_bypassed(client, db):
    blocked = Visit(
        url=FLIGHTS, ok=False, failure="o site pediu para provar que não é robô; não contornei isso"
    )
    llm, _ = world(client, db, plan={"browse": True, "urls": [FLIGHTS]}, pages={FLIGHTS: blocked})
    headers = _login(client, db)
    _, turn = _send(client, headers, "quanto tá a passagem pra Santiago?")
    message = _chat_prompt(llm)[-1].content
    assert "Não abriu: o site pediu para provar que não é robô; não contornei isso" in message
    assert turn["sources"] == []


def test_talk_that_is_not_about_live_data_never_plans_or_opens_anything(client, db):
    llm, browser = world(client, db, plan={"browse": True, "urls": [FLIGHTS]}, pages={})
    headers = _login(client, db)
    _send(client, headers, "bom dia, tudo bem?")
    assert browser.opened == []
    assert all(p[0].content != browse.INSTRUCTIONS for p in llm.prompts)


def test_when_the_plan_says_no_nothing_opens(client, db):
    _, browser = world(client, db, plan={"browse": False, "why": "falta a data"}, pages={})
    headers = _login(client, db)
    _send(client, headers, "quero ver passagem pra Santiago")
    assert browser.opened == []


def test_login_pages_and_private_addresses_are_never_opened(client, db):
    plan = {
        "browse": True,
        "urls": [
            "https://www.booking.com/login.html",
            "https://127.0.0.1/admin",
            "http://example.com/preco",
            FLIGHTS,
        ],
    }
    _, browser = world(client, db, plan=plan, pages={})
    headers = _login(client, db)
    _send(client, headers, "compara o preço desses sites")
    assert browser.opened == [FLIGHTS]


def test_without_a_browser_it_does_not_claim_it_can_browse(client, db):
    llm, _ = world(client, db, plan={"browse": True, "urls": [FLIGHTS]}, pages={})
    client.app.dependency_overrides[get_browser] = lambda: None
    headers = _login(client, db)
    _send(client, headers, "quanto custa a passagem?")
    assert "abrir sites ao vivo" not in _chat_prompt(llm)[0].content


def test_only_public_https_requests_are_allowed():
    cache = {}
    assert not allowed_request("https://127.0.0.1/", cache)
    assert not allowed_request("https://10.0.0.5/x", cache)
    assert not allowed_request("https://[::1]/", cache)
    assert not allowed_request("http://8.8.8.8/", cache)
    assert not allowed_request("https://user:senha@8.8.8.8/", cache)
    assert not allowed_request("https://8.8.8.8:8443/", cache)
    assert not allowed_request("file:///etc/passwd", cache)
    assert allowed_request("data:image/png;base64,AAAA", cache)
    assert allowed_request("https://8.8.8.8/", cache)
