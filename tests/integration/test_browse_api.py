"""Live pages: opened only when the message is about something that changes (fares, prices),
read only, given to the model as third-party data with the time read, listed as sources and kept
on record. A site that asks to prove you are human is reported, never worked around."""

import json
from datetime import UTC, datetime

import pytest

from apps.api.browser import get_browser
from apps.api.llm import get_llm_provider
from apps.api.search import get_search_provider
from apps.api.settings import Settings, get_settings
from core import browse
from core.curiosity.engine import ASSESSMENT_INSTRUCTIONS
from core.decision import record
from core.identity.genesis import run_genesis
from infrastructure.database.models import BrowseVisit, Decision, Panel, PanelOffer
from integrations.browser.base import Visit
from integrations.browser.playwright_browser import allowed_request
from integrations.search.base import SearchResult
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


class FakeSearch:
    name = "fake"

    def __init__(self, urls):
        self.urls, self.queries = urls, []

    def search(self, query, max_results):
        self.queries.append(query)
        now = datetime.now(UTC)
        return [SearchResult(u, u, "", "fake", now) for u in self.urls[:max_results]]


def world(
    client, db, *, plan, pages, reply="Achei voos a partir de R$ 2.195 por pessoa.", search=None
):
    """`plan` may be a list (one plan per planning call, in order) or a raw string."""
    plans = list(plan) if isinstance(plan, list) else None

    def respond(messages):
        if messages[0].content == browse.INSTRUCTIONS:
            chosen = plans.pop(0) if plans else plan
            return chosen if isinstance(chosen, str) else json.dumps(chosen)
        return reply

    llm = FakeLLMProvider(responder=respond)
    browser = FakeBrowser(pages)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_browser] = lambda: browser
    if search is not None:
        client.app.dependency_overrides[get_search_provider] = lambda: search
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


REFUSED = Visit(url="https://tracxn.com/d/casal", ok=False, failure="o site respondeu 403")
OPEN = Visit(url="https://casal.com.br/sobre", ok=True, title="Casal", text="Fundada em 1998")


def _plans(llm):
    return [json.loads(p[-1].content) for p in llm.prompts if p[0].content == browse.INSTRUCTIONS]


def _actions(db):
    return [a for d in db.query(Decision).all() for a in d.actions]


def test_a_site_that_refuses_the_robot_is_replaced_by_a_spare_search_result(client, db):
    """Real case (2026-11-16): tracxn and rocketreach answered 403 and nothing else was tried."""
    search = FakeSearch([REFUSED.url, "https://rocketreach.co/casal", OPEN.url])
    pages = {
        REFUSED.url: REFUSED,
        "https://rocketreach.co/casal": Visit(
            url="https://rocketreach.co/casal",
            ok=False,
            failure="o site pediu para provar que não é robô; não contornei isso",
        ),
        OPEN.url: OPEN,
    }
    plan = {"browse": True, "urls": [], "search": "Casal empresa"}
    llm, browser = world(client, db, plan=plan, pages=pages, search=search)
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        curiosity_enabled=False, browser_max_pages=2
    )
    headers = _login(client, db)

    _send(client, headers, "procura na internet o preço da Casal")

    assert browser.opened == [REFUSED.url, "https://rocketreach.co/casal", OPEN.url]
    assert len(_plans(llm)) == 1  # the spare was enough: no second plan
    message = _chat_prompt(llm)[-1].content
    assert "Fundada em 1998" in message and "abri outro site no lugar" in message


def test_without_spares_a_second_plan_knows_which_sites_refused(client, db):
    plans = [
        {"browse": True, "urls": [REFUSED.url], "search": ""},
        {"browse": True, "urls": [REFUSED.url, OPEN.url], "search": ""},
    ]
    llm, browser = world(client, db, plan=plans, pages={REFUSED.url: REFUSED, OPEN.url: OPEN})
    headers = _login(client, db)

    _send(client, headers, "procura na internet o preço da Casal")

    assert _plans(llm)[1]["refused"] == ["tracxn.com"]
    assert browser.opened == [REFUSED.url, OPEN.url]  # never the refused one twice


def test_sites_that_refused_lately_are_named_in_the_next_plan(client, db):
    search = FakeSearch([REFUSED.url, OPEN.url])
    plan = {"browse": True, "urls": [], "search": "Casal"}
    llm, browser = world(
        client, db, plan=plan, pages={REFUSED.url: REFUSED, OPEN.url: OPEN}, search=search
    )
    headers = _login(client, db)
    conversation, _ = _send(client, headers, "procura na internet o preço da Casal")
    browser.opened.clear()

    _send(client, headers, "e quanto tá agora no site?", conversation)

    assert _plans(llm)[-1]["refused"] == ["tracxn.com"]
    assert browser.opened == [OPEN.url]  # its search result is dropped before opening


def test_a_page_that_is_only_broken_is_not_retried_elsewhere(client, db):
    llm, browser = world(client, db, plan={"browse": True, "urls": [FLIGHTS]}, pages={})
    headers = _login(client, db)
    _send(client, headers, "quanto tá a passagem pra Santiago?")
    assert browser.opened == [FLIGHTS] and len(_plans(llm)) == 1


@pytest.mark.parametrize(
    ("plan", "reason"),
    [
        ("não sei", "planner_invalid_json"),
        ({"browse": False, "why": "dá para estimar", "missing": []}, "planner_declined"),
        ({"browse": True, "urls": [], "search": ""}, "no_addresses"),
    ],
)
def test_giving_up_after_planning_is_on_record_with_the_reason(client, db, plan, reason):
    llm, browser = world(client, db, plan=plan, pages={})
    headers = _login(client, db)

    _send(client, headers, "o preço sobe muito se eu pegar aulas de esqui?")

    assert browser.opened == []
    skipped = [a for a in _actions(db) if a["action"] == "browse_skipped"]
    assert [(a["reason"], a["about_prices"]) for a in skipped] == [(reason, True)]
    if reason == "planner_declined":
        assert skipped[0]["why"] == "dá para estimar"


def test_a_price_question_it_gave_up_on_never_denies_the_browser(client, db):
    """Real case (2026-11-16): "o preço sobe muito se eu pegar aulas?" got "não tenho preços
    atuais" from the reply, with the browser working: the plan had said no, silently."""
    llm, _ = world(client, db, plan={"browse": False, "missing": []}, pages={})
    headers = _login(client, db)
    _send(client, headers, "o preço sobe muito se eu pegar aulas de esqui?")
    system = _chat_prompt(llm)[0].content
    assert "Nunca diga que não tem acesso a preços atuais" in system

    llm.responder = lambda messages: (
        "não sei" if messages[0].content == browse.INSTRUCTIONS else "ok"
    )
    _send(client, headers, "e quanto custa a diária do hotel lá?")
    system = _chat_prompt(llm)[0].content
    assert "tentou consultar preços ao vivo agora" in system
    assert "voltou ilegível" in system


def test_when_the_budget_stops_the_second_plan_it_is_on_record(client, db, monkeypatch):
    calls = []

    def budget_after_first(session, conversation, budgets):
        calls.append(1)
        if len(calls) > 1:
            raise browse.BudgetExceededError("daily", 1, 1)

    monkeypatch.setattr(browse, "check_budgets", budget_after_first)
    _, browser = world(
        client, db, plan={"browse": True, "urls": [REFUSED.url]}, pages={REFUSED.url: REFUSED}
    )
    headers = _login(client, db)
    _send(client, headers, "procura na internet o preço da Casal")
    assert browser.opened == [REFUSED.url]
    skipped = [a for a in _actions(db) if a["action"] == "browse_skipped"]
    assert [(a["reason"], a.get("retry")) for a in skipped] == [("budget", True)]


def test_a_cut_plan_is_told_apart_from_an_unreadable_one(client, db):
    llm, _ = world(client, db, plan='{"browse": true, "urls": ["https://', pages={})
    llm.finish_reason = "length"
    headers = _login(client, db)
    _send(client, headers, "quanto tá a passagem pra Santiago em agosto?")
    reasons = [a["reason"] for a in _actions(db) if a["action"] == "browse_skipped"]
    assert reasons == ["planner_truncated"]


def test_a_skip_on_talk_that_is_not_about_prices_adds_nothing_to_the_reply(client, db):
    llm, _ = world(client, db, plan={"browse": False, "missing": []}, pages={})
    headers = _login(client, db)
    _send(client, headers, "vou comprar o domínio hoje")
    system = _chat_prompt(llm)[0].content
    assert "nesta mensagem nada foi aberto" not in system
    assert "tentou consultar preços ao vivo agora" not in system
    reasons = [a["reason"] for a in _actions(db) if a["action"] == "browse_skipped"]
    assert reasons == ["planner_declined"]


def test_a_near_miss_in_a_price_conversation_is_logged_at_debug(client, db, caplog):
    """Not a decision (every message passes the word check), but worth seeing: a follow-up in a
    conversation about fares that did not even reach the planner. Never the message text."""
    llm, browser = world(client, db, plan={"browse": False, "missing": []}, pages={})
    headers = _login(client, db)
    conversation, _ = _send(client, headers, "quanto custa a passagem pra Santiago?")

    with caplog.at_level("DEBUG", logger="core.browse"):
        _send(client, headers, "acho que vou gostar muito de lá", conversation)

    near = [r for r in caplog.records if getattr(r, "event", "") == "browse_not_candidate"]
    assert len(near) == 1 and near[0].levelname == "DEBUG"
    assert near[0].recent_topic == "quanto custa" and near[0].chars == 31
    assert "gostar" not in near[0].getMessage()
    # Only the first turn reached the planner (and was declined): the near miss is no decision.
    assert [a["action"] for a in _actions(db)].count("browse_skipped") == 1


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


def test_the_bench_shows_what_it_did_the_pages_and_the_live_sites(client, db):
    page = Visit(
        url=FLIGHTS, ok=True, final_url=FLIGHTS, title="CNF a SCL | Google Voos", text="R$ 2.195"
    )
    world(client, db, plan={"browse": True, "urls": [FLIGHTS]}, pages={FLIGHTS: page})
    headers = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    conversation, _ = _send(client, headers, "quanto tá a passagem pra Santiago?")

    bench = client.get(f"/conversations/{conversation}/bench", headers=headers).json()

    assert bench["deeds"][-1]["text"] == "abriu num navegador de verdade google.com (1 página(s))"
    assert bench["visits"][0] == {
        "title": "CNF a SCL | Google Voos",
        "url": FLIGHTS,
        "at": bench["visits"][0]["at"],
    }
    assert bench["pages"] == []
    assert client.get(f"/conversations/{conversation}/bench", headers=other).status_code == 404


def test_the_video_trip_asks_for_origin_and_dates_instead_of_denying_live_prices(client, db):
    """Real case (14/11/2026): with the browser ready, "quanto custa viajar pro Chile em agosto
    de 2027 a dois?" got a price range from an article and "não tenho acesso a sites de venda ao
    vivo", with sources about a poet and an insurer. Then "Então não consegue cotar em tempo
    real?" got the same denial."""
    page = Visit(url=FLIGHTS, ok=True, final_url=FLIGHTS, title="Google Voos", text="R$ 2.195")
    planner_saw = []

    def respond(messages):
        system = messages[0].content
        if system == browse.INSTRUCTIONS:
            data = json.loads(messages[-1].content)
            planner_saw.append(data)
            if "BH" in data["message"]:
                return json.dumps({"browse": True, "urls": [FLIGHTS], "missing": []})
            return json.dumps({"browse": False, "missing": ["origem", "datas"]})
        if ASSESSMENT_INSTRUCTIONS[:60] in system:
            raise AssertionError("no web research while the trip waits for its details")
        if "falta: origem, datas" in system:
            return "Consigo ver os preços de agora nos sites. De onde vocês saem e em que dias?"
        return "Não tenho acesso a sites de venda ao vivo."

    llm = FakeLLMProvider(responder=respond)
    browser = FakeBrowser({FLIGHTS: page})
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_browser] = lambda: browser
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=True)
    run_genesis(db)
    db.commit()
    headers = _login(client, db)

    conversation, turn = _send(
        client, headers, "quanto custa viajar pro Chile em agosto de 2027 a dois?"
    )
    reply = turn["assistant_message"]["content"]
    assert "não tenho acesso" not in reply.lower()
    assert "De onde" in reply and "dias" in reply
    assert browser.opened == [] and turn["sources"] == []
    system = _chat_prompt(llm)[0].content
    assert "Nunca diga que não tem acesso a sites ou a preços ao vivo" in system
    assert "abrir sites ao vivo num navegador de verdade" in system

    _, turn = _send(client, headers, "Então não consegue cotar em tempo real?", conversation)
    assert "não tenho acesso" not in turn["assistant_message"]["content"].lower()

    # The details arrive: it browses without the question being asked again.
    _send(client, headers, "saindo de BH, de 10 a 17 de agosto", conversation)
    assert browser.opened == [FLIGHTS]
    assert "quanto custa viajar pro Chile" in planner_saw[-1]["recent_conversation"]


def test_without_a_browser_the_missing_details_never_reach_the_reply(client, db):
    llm, _ = world(client, db, plan={"browse": False, "missing": ["origem"]}, pages={}, reply="ok")
    client.app.dependency_overrides[get_browser] = lambda: None
    headers = _login(client, db)
    _send(client, headers, "quanto custa viajar pro Chile?")
    assert "falta:" not in _chat_prompt(llm)[0].content
    assert all(p[0].content != browse.INSTRUCTIONS for p in llm.prompts)


def test_a_reply_in_bubbles_is_one_message_with_parts(client, db):
    world(
        client,
        db,
        plan={"browse": False, "missing": ["origem"]},
        pages={},
        reply="Consigo ver os preços de agora.\n[[+]]\nDe onde vocês saem?",
    )
    headers = _login(client, db)
    conversation, turn = _send(client, headers, "quanto custa viajar pro Chile?")
    message = turn["assistant_message"]
    assert message["parts"] == ["Consigo ver os preços de agora.", "De onde vocês saem?"]
    assert message["content"] == "Consigo ver os preços de agora.\n\nDe onde vocês saem?"
    listed = client.get(f"/conversations/{conversation}/messages", headers=headers).json()
    assert listed[-1]["parts"] == message["parts"]


def _offer_world(client, db):
    page = Visit(
        url=FLIGHTS, ok=True, final_url=FLIGHTS, title="Google Voos", text="LATAM R$ 2.195"
    )

    def respond(messages):
        if messages[0].content == browse.INSTRUCTIONS:
            return json.dumps({"browse": True, "urls": [FLIGHTS], "title": "Combo Santiago"})
        if "A pessoa aceitou o painel" in messages[0].content:
            return "Pronto, estou montando o Combo Santiago."
        return "LATAM a R$ 2.195 no Google Voos, agora. Quer que eu deixe isso num painel?"

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_browser] = lambda: FakeBrowser({FLIGHTS: page})
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm


def test_a_live_quote_ends_with_a_panel_offer_that_cites_the_budget(client, db):
    llm = _offer_world(client, db)
    headers = _login(client, db)
    conversation, turn = _send(
        client, headers, "quanto tá a passagem de Confins pra Santiago? quero gastar até R$ 6 mil"
    )
    assert "Quer que eu deixe" in turn["assistant_message"]["content"]
    assert "meta de R$ 6.000" in _chat_prompt(llm)[0].content
    offers = client.get("/panels/offers", headers=headers).json()
    assert len(offers) == 1 and offers[0]["title"] == "Combo Santiago"
    assert offers[0]["goal_amount"] == "6000.00"
    assert offers[0]["message_id"] == turn["assistant_message"]["id"]
    assert offers[0]["conversation_id"] == conversation


def test_a_plain_yes_accepts_the_offer_and_the_panel_is_made(client, db):
    llm = _offer_world(client, db)
    headers = _login(client, db)
    conversation, _ = _send(client, headers, "quanto tá a passagem pra Santiago?")
    _, turn = _send(client, headers, "por favor", conversation)
    assert any("já está no Início" in prompt[0].content for prompt in llm.prompts)
    assert turn["assistant_message"]["artifact"] is None  # a live panel now, not a page
    assert db.query(Panel).one().title == "Combo Santiago"
    assert client.get("/panels/offers", headers=headers).json() == []
    assert db.query(PanelOffer).one().status == "accepted"


def test_a_tap_accepts_and_another_owner_cannot(client, db):
    _offer_world(client, db)
    headers = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    _send(client, headers, "quanto tá a passagem pra Santiago?")
    offer = client.get("/panels/offers", headers=headers).json()[0]
    assert client.post(f"/panels/offers/{offer['id']}/approve", headers=other).status_code == 404
    done = client.post(f"/panels/offers/{offer['id']}/approve", headers=headers).json()
    assert done["status"] == "accepted" and done["panel_id"]
    again = client.post(f"/panels/offers/{offer['id']}/approve", headers=headers)
    assert again.status_code == 404


def test_a_yes_to_something_else_does_not_accept_an_old_offer(client, db):
    _offer_world(client, db)
    headers = _login(client, db)
    conversation, _ = _send(client, headers, "quanto tá a passagem pra Santiago?")
    _send(client, headers, "legal, obrigado", conversation)
    _send(client, headers, "pode", conversation)
    assert db.query(PanelOffer).one().status == "proposed"


def test_pages_without_prices_make_no_offer(client, db):
    page = Visit(url=FLIGHTS, ok=True, final_url=FLIGHTS, title="Voos", text="Sem voos.")
    world(client, db, plan={"browse": True, "urls": [FLIGHTS]}, pages={FLIGHTS: page})
    headers = _login(client, db)
    _send(client, headers, "quanto tá a passagem pra Santiago?")
    assert client.get("/panels/offers", headers=headers).json() == []
