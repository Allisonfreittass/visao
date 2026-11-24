"""Live panels end to end (docs/PAINEIS.md, ADR-0012), with recorded pages and no network: made
from the offer, edited from the conversation, checked daily by the worker within the pause and
the budget, notices only when something relevant changes, expired after the trip."""

import json
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from apps.api.browser import get_browser
from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from apps.worker.handlers import panel_handler
from core import browse
from core.identity.genesis import run_genesis
from core.panels import editing, extract
from core.panels import service as panels
from core.panels.service import Limits
from core.policies.autonomy import set_paused
from infrastructure.database.models import (
    AgentIdentity,
    AuditLog,
    Conversation,
    ModelUsage,
    Panel,
    PanelSnapshot,
    PanelVersion,
    ScheduledJob,
    User,
)
from integrations.browser.base import Visit
from tests.fakes import FakeLLMProvider
from tests.integration.test_browse_api import FakeBrowser
from tests.integration.test_curiosity_api import _login

FIXTURES = Path(__file__).parent.parent / "fixtures" / "panels"
FLIGHTS = (
    "https://www.google.com/travel/flights?q=Flights%20to%20SCL%20from%20CNF%20on%202027-08-14"
    "%20through%202027-08-21&hl=pt-BR&curr=BRL"
)
FLIGHT_TEXT = (FIXTURES / "google_flights_cnf_scl.txt").read_text()
HOTEL_TEXT = (FIXTURES / "google_hotels_providencia.txt").read_text()
SPEC = {
    "origin": "Belo Horizonte",
    "origin_code": "CNF",
    "destination": "Santiago",
    "destination_code": "SCL",
    "depart": "2027-08-14",
    "back": "2027-08-21",
    "travelers": 2,
    "hotel_area": "Providencia",
    "preferences": ["hostel"],
    "include": ["flight", "hotel"],
}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(browse, "allowed_request", lambda url, cache: url.startswith("https://"))


class Prices:
    """What the fake model answers to an extraction: the cheapest it 'sees' on each page."""

    def __init__(self):
        self.flight, self.hotel = 4390, 1555

    def answer(self, messages):
        payload = json.loads(messages[-1].content)
        items = []
        for page in payload["pages"]:
            if "Voos" in page["text"]:
                items.append(
                    {
                        "kind": "flight",
                        "provider": "LATAM",
                        "where": "CNF → SCL",
                        "connections": 1,
                        "price": self.flight,
                        "visit_id": page["visit_id"],
                    }
                )
            elif "Hotéis" in page["text"]:
                items.append(
                    {
                        "kind": "hotel",
                        "provider": "Hostal Providencia",
                        "where": "Providencia",
                        "price": self.hotel,
                        "visit_id": page["visit_id"],
                    }
                )
        return json.dumps({"spec": SPEC if payload["want_spec"] else None, "items": items})


class AnyPage(FakeBrowser):
    """Opens any Google Flights/Hotels address with the recorded text (or a robot check)."""

    def __init__(self, robot=False):
        super().__init__({})
        self.robot = robot

    def visit(self, urls, on_visit=None):
        self.opened += urls
        if self.robot:
            return [
                Visit(url=u, ok=False, failure="o site pediu para provar que não é robô")
                for u in urls
            ]
        return [
            Visit(
                url=u,
                ok=True,
                final_url=u,
                title="Google Voos" if "flights" in u else "Google Hotéis",
                text=FLIGHT_TEXT if "flights" in u else HOTEL_TEXT,
            )
            for u in urls
        ]


def world(client, db, prices=None, browser=None):
    prices = prices or Prices()
    browser = browser or AnyPage()

    def respond(messages):
        system = messages[0].content
        if system == browse.INSTRUCTIONS:
            return json.dumps({"browse": True, "urls": [FLIGHTS], "title": "Combo Santiago"})
        if system == extract.INSTRUCTIONS:
            return prices.answer(messages)
        if system == editing.INSTRUCTIONS:
            if "Lastarria" not in messages[-1].content:
                return json.dumps({"changes": {}, "title": None})
            return json.dumps({"changes": {"hotel_area": "Lastarria"}, "title": None})
        if "já está no Início" in system:
            return "Pronto, o Combo Santiago está no Início."
        if "foi atualizado agora" in system:
            return "Feito: troquei o bairro do hotel."
        return "LATAM a R$ 4.390 no Google Voos, agora. Quer um painel no Início?"

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_browser] = lambda: browser
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm, prices, browser


def send(client, headers, text, conversation=None):
    conversation = conversation or client.post("/conversations", headers=headers).json()["id"]
    turn = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": text}
    )
    assert turn.status_code == 200, turn.text
    return conversation, turn.json()


def make_panel(client, db, headers):
    conversation, _ = send(
        client, headers, "quanto custa ir de BH pra Santiago de 14 a 21 de agosto? até R$ 6 mil"
    )
    _, turn = send(client, headers, "por favor", conversation)
    return conversation, db.query(Panel).one(), turn


def test_a_yes_makes_a_live_panel_with_the_total_and_the_goal(client, db):
    world(client, db)
    headers = _login(client, db)
    _, panel, turn = make_panel(client, db, headers)

    assert "está no Início" in turn["assistant_message"]["content"]
    card = client.get("/panels", headers=headers).json()[0]
    assert card["title"] == "Combo Santiago" and card["status"] == "active"
    # Only the flight page was read in the conversation: the stay is still to be confirmed.
    assert card["total"] is None and Decimal(card["items"][0]["price"]) == 4390
    assert card["goal"] == "6000.00" and card["checked_today"] is True
    assert (
        db.query(AuditLog).filter_by(action="panel.create").one().details["recurring_check"]
        == "daily"
    )
    job = db.query(ScheduledJob).filter_by(kind=panels.JOB_KIND).one()
    assert job.run_after.replace(tzinfo=UTC) > datetime.now(UTC)


@pytest.fixture
def daytime(monkeypatch):
    """These checks alert, and an alert waits out the owner's quiet hours (22:00 to 08:00 in São
    Paulo): they run at a daytime hour whatever the real clock says (they failed between 21:00
    and midnight there, when CI happened to run)."""
    real = datetime.now(UTC)
    local = real.astimezone(ZoneInfo("America/Sao_Paulo"))
    if not 9 <= local.hour < 21:
        day = local.date() + timedelta(days=1 if local.hour >= 21 else 0)
        real = datetime.combine(day, time(12), tzinfo=local.tzinfo).astimezone(UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return real.astimezone(tz) if tz else real.replace(tzinfo=None)

    monkeypatch.setattr(panels, "datetime", Clock)
    return real


def recheck_now(db, llm, browser, **overrides):
    panel = db.query(Panel).one()
    owner = db.get(User, panel.owner_user_id)
    return panels.recheck(
        db,
        panel,
        owner=owner,
        browser=browser,
        provider=llm,
        limits=overrides.pop("limits", Limits()),
        has_room=overrides.pop("has_room", lambda: True),
        **overrides,
    )


def test_the_daily_check_reads_both_pages_and_computes_the_goal(client, db, daytime):
    llm, _, browser = world(client, db)
    headers = _login(client, db)
    make_panel(client, db, headers)

    # The total is known for the first time, and below the goal: the urgent notice.
    assert recheck_now(db, llm, browser) == "alerted"

    card = client.get("/panels", headers=headers).json()[0]
    assert card["total"] == "5945.00"
    assert card["goal_words"] == "R$ 55 abaixo da meta de R$ 6.000"
    assert any("flights" in u for u in browser.opened) and any(
        "search" in u for u in browser.opened
    )
    assert db.query(PanelSnapshot).count() == 2


BELOW = "Abaixo da sua meta de R$ 6.000: R$ 5.945 agora. Preço de site muda rápido."


def test_below_the_goal_is_urgent_once_each_time_and_drops_once_a_day(
    client, db, monkeypatch, daytime
):
    llm, prices, browser = world(client, db)
    sent = []
    monkeypatch.setattr(panels.push, "send_to_owner", lambda *a, **k: sent.append(k["body"]) or 1)
    headers = _login(client, db)
    make_panel(client, db, headers)
    prices.flight, prices.hotel = 4812, 1555  # 6367: above the goal
    recheck_now(db, llm, browser)
    assert sent == []
    prices.flight = 4390  # 5945: below the goal
    assert recheck_now(db, llm, browser) == "alerted"
    assert sent == [BELOW]
    prices.hotel = 1388  # another drop the same day, still below: no second notice
    assert recheck_now(db, llm, browser) == "checked" and len(sent) == 1
    prices.flight, prices.hotel = 4812, 1555  # back above...
    assert recheck_now(db, llm, browser) == "checked"
    prices.flight = 4390  # ...and below again, the same day: urgent skips the one-a-day limit
    assert recheck_now(db, llm, browser) == "alerted" and sent[-1] == BELOW and len(sent) == 2


# 12:00 in São Paulo; quiet hours 22:00 to 08:00 (the default).
NOON = datetime(2026, 11, 17, 15, 0, tzinfo=UTC)


def _sao_paulo(db):
    owner = db.query(User).one()
    owner.timezone, owner.quiet_start, owner.quiet_end = "America/Sao_Paulo", "22:00", "08:00"
    db.commit()


def test_near_the_goal_it_checks_every_few_hours_outside_quiet_hours(client, db, monkeypatch):
    llm, prices, browser = world(client, db)
    monkeypatch.setattr(panels.push, "send_to_owner", lambda *a, **k: 1)
    headers = _login(client, db)
    make_panel(client, db, headers)
    _sao_paulo(db)
    panel = db.query(Panel).one()

    prices.flight = 9000  # far above the goal: once a day, tomorrow at 9h
    recheck_now(db, llm, browser, now=NOON)
    assert panel.next_check_at.replace(tzinfo=UTC) == datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    assert client.get("/panels", headers=headers).json()[0]["watch_every_hours"] is None

    prices.flight = 4812  # 6% above the goal: in 3 hours
    recheck_now(db, llm, browser, now=NOON)
    assert panel.next_check_at.replace(tzinfo=UTC) == NOON + timedelta(hours=3)
    assert client.get("/panels", headers=headers).json()[0]["watch_every_hours"] == 3

    evening = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)  # 21:00: 3 hours later is quiet
    recheck_now(db, llm, browser, now=evening)
    assert panel.next_check_at.replace(tzinfo=UTC) == datetime(2026, 11, 18, 11, 0, tzinfo=UTC)
    jobs = db.query(ScheduledJob).filter_by(kind=panels.JOB_KIND).all()
    # Every job but the latest was moved since: those do nothing when they come.
    assert len([j for j in jobs if panels.stale(panel, j.payload["at"])]) == len(jobs) - 1


def test_an_urgent_notice_in_quiet_hours_waits_for_the_first_check_after(client, db, monkeypatch):
    llm, prices, browser = world(client, db)
    sent = []
    monkeypatch.setattr(panels.push, "send_to_owner", lambda *a, **k: sent.append(k["body"]) or 1)
    headers = _login(client, db)
    make_panel(client, db, headers)
    _sao_paulo(db)
    night = datetime(2026, 11, 18, 4, 0, tzinfo=UTC)  # 01:00 in São Paulo

    assert recheck_now(db, llm, browser, now=night) == "checked" and sent == []
    panel = db.query(Panel).one()
    assert panel.goal_alerted_at is None
    morning = panel.next_check_at.replace(tzinfo=UTC)
    assert morning == datetime(2026, 11, 18, 11, 0, tzinfo=UTC)  # 08:00, when quiet hours end
    assert recheck_now(db, llm, browser, now=morning) == "alerted" and sent == [BELOW]


@pytest.mark.parametrize(
    ("text", "goal"),
    [
        ("me avisa se ficar abaixo de R$ 5.500", Decimal("5500.00")),
        ("me avisa se cair pra 5 mil", Decimal("5000.00")),
        ("me alerta quando chegar a R$ 4.800,50", Decimal("4800.50")),
        ("quanto custa um hotel por menos de R$ 500?", None),
        ("me avisa amanhã", None),
    ],
)
def test_a_notice_said_with_a_number_is_a_goal(text, goal):
    from core.panels.offers import goal_from

    assert goal_from(text) == goal


def test_asking_for_a_notice_sets_the_goal_of_the_panel(client, db):
    llm, prices, browser = world(client, db)
    headers = _login(client, db)
    conversation, panel, _ = make_panel(client, db, headers)
    recheck_now(db, llm, browser)  # 5945

    _, turn = send(client, headers, "me avisa se ficar abaixo de R$ 5.500", conversation)

    db.refresh(panel)
    assert panel.spec["goal"] == "5500.00" and panel.spec["hotel_area"] == "Providencia"
    system = llm.prompts[-1][0].content
    assert "Agora está R$ 445 acima da meta de R$ 5.500" in system
    assert "confiro a cada 3 h" in system
    assert client.get("/panels", headers=headers).json()[0]["watch_every_hours"] == 3
    # Inside a new quote, the same words are that quote's goal, not the old panel's.
    assert not editing.wants_edit(
        "quero ver voo pra Lima em março, de BH, 2 pessoas, e me avisa se cair pra R$ 3 mil"
    )


def test_a_robot_check_is_reported_and_never_worked_around(client, db):
    llm, _, _ = world(client, db)
    headers = _login(client, db)
    make_panel(client, db, headers)
    assert recheck_now(db, llm, AnyPage(robot=True)) == "failed"
    card = client.get("/panels", headers=headers).json()[0]
    assert "verificação de robô" in card["note"]
    assert Decimal(card["items"][0]["price"]) == 4390  # the last check stays, with its hour


def test_pause_and_budget_stop_the_check_without_a_stale_price_as_today(client, db):
    llm, _, browser = world(client, db)
    headers = _login(client, db)
    make_panel(client, db, headers)
    assert recheck_now(db, llm, browser, has_room=lambda: False) == "no_budget"
    set_paused(db, True, actor_user_id=None, reason="teste")
    db.commit()
    assert recheck_now(db, llm, browser) == "paused"
    panel = db.query(Panel).one()
    panel.checked_at = datetime.now(UTC) - timedelta(days=2)
    db.commit()
    card = client.get("/panels", headers=headers).json()[0]
    assert card["checked_today"] is False and "pausada" in card["note"]


def test_a_panel_expires_after_the_trip(client, db):
    llm, _, browser = world(client, db)
    headers = _login(client, db)
    make_panel(client, db, headers)
    later = datetime(2027, 8, 23, 12, tzinfo=UTC)
    assert recheck_now(db, llm, browser, now=later) == "expired"
    assert client.get("/panels", headers=headers).json() == []


def test_the_owner_edits_the_same_panel_and_the_old_version_stays(client, db, steps):
    llm, _, browser = world(client, db)
    headers = _login(client, db)
    conversation, panel, _ = make_panel(client, db, headers)

    _, turn = send(
        client, headers, "troca o hotel pra Lastarria e muda a meta pra R$ 5.500", conversation
    )

    db.refresh(panel)
    assert panel.spec["hotel_area"] == "Lastarria" and panel.spec["goal"] == "5500.00"
    assert panel.version == 2 and db.query(Panel).count() == 1
    old = db.query(PanelVersion).one()
    assert old.spec["hotel_area"] != "Lastarria" and old.version == 1
    assert "troquei" in turn["assistant_message"]["content"]
    assert any("Lastarria" in u for u in browser.opened)  # checked again with the change
    assert ("Conferindo os preços de novo", "site") in steps


def test_pause_resume_and_delete_belong_to_the_owner(client, db):
    world(client, db)
    headers = _login(client, db)
    other = _login(client, db, "b@exemplo.com")
    _, panel, _ = make_panel(client, db, headers)
    url = f"/panels/{panel.id}"
    assert client.patch(url, headers=other, json={"status": "paused"}).status_code == 404
    assert (
        client.patch(url, headers=headers, json={"status": "paused"}).json()["status"] == "paused"
    )
    assert (
        client.patch(url, headers=headers, json={"status": "active"}).json()["status"] == "active"
    )
    detail = client.get(url, headers=headers).json()
    assert len(detail["history"]) == 1
    assert client.delete(url, headers=other).status_code == 404
    assert client.delete(url, headers=headers).status_code == 204
    assert client.get("/panels", headers=headers).json() == []


def test_no_more_than_the_limit_of_active_panels(client, db, monkeypatch):
    world(client, db)
    monkeypatch.setattr(panels, "active_count", lambda session, owner_id: 3)
    headers = _login(client, db)
    conversation, _ = send(client, headers, "quanto tá a passagem pra Santiago? até R$ 6 mil")
    send(client, headers, "pode", conversation)
    assert db.query(Panel).count() == 0


def test_the_worker_job_runs_the_check(client, db, monkeypatch, daytime):
    llm, _, browser = world(client, db)
    headers = _login(client, db)
    make_panel(client, db, headers)
    monkeypatch.setattr("apps.worker.handlers.get_browser", lambda: browser)
    monkeypatch.setattr("apps.worker.handlers.autonomy_room", lambda session, settings: True)
    job = db.query(ScheduledJob).filter_by(kind=panels.JOB_KIND).one()
    result = panel_handler(Settings(), llm)(db, job)
    assert result.result["outcome"] == "alerted"  # 5945: below the goal of 6000
    # Counted as the agent's own call, in the autonomy budget.
    assert db.query(ModelUsage).filter_by(purpose="panel_recheck").count() == 1
    # The first job was for a check that has since moved: it does nothing.
    assert panel_handler(Settings(), llm)(db, job).result == {"skipped": "moved"}


def test_suggestions_come_from_recent_titles_and_skip_sensitive_ones(client, db):
    world(client, db)
    headers = _login(client, db)
    owner = db.query(User).one()
    identity = db.query(AgentIdentity).one()
    for title in ("Passagem pra Lisboa em maio", "Consulta médica e exames", "Bom dia"):
        db.add(Conversation(user_id=owner.id, identity_id=identity.id, title=title))
    db.commit()
    texts = [s["text"] for s in client.get("/panels/suggestions", headers=headers).json()]
    assert texts == ["Acompanhar o preço: Passagem pra Lisboa em maio"]
