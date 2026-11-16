"""The morning briefing (docs/RESUMO_DA_MANHA.md, ADR-0017): one message when quiet hours end,
from facts gathered in code, worded by the model and refused when it invents a sum of money."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from core.identity.capabilities import Capabilities
from core.mind import briefing
from core.panels import service as panels
from infrastructure.database.models import Conversation, Message, Panel, ScheduledJob, User
from tests.integration.test_curiosity_api import _login
from tests.integration.test_panels_api import (  # noqa: F401 - offline is an autouse fixture
    make_panel,
    offline,
    world,
)

# 08:00 in São Paulo, when the default quiet hours (22:00 to 08:00) end.
MORNING = datetime(2026, 11, 18, 11, 0, tzinfo=UTC)
BUDGET = briefing.AutonomyBudget(
    llm_calls_per_day=50,
    tokens_per_day=10_000_000,
    max_actions_per_cycle=10,
    max_seconds=60,
    research_per_day=5,
    max_output_tokens=900,
    daily_usd=Decimal("5"),
)


def _owner(db) -> User:
    owner = db.query(User).one()
    owner.timezone, owner.quiet_start, owner.quiet_end = "America/Sao_Paulo", "22:00", "08:00"
    db.commit()
    return owner


def _say(llm, text):
    """The fake model answers the briefing with `text` and everything else as before."""
    before = llm.responder

    def respond(messages):
        if messages[0].content == briefing.INSTRUCTIONS:
            return json.dumps({"say": text})
        return before(messages)

    llm.responder = respond


def _run(db, llm, browser, owner, **extra):
    return briefing.run(
        db,
        owner,
        now=extra.pop("now", MORNING),
        provider=llm,
        budget=BUDGET,
        browser=browser,
        limits=panels.Limits(),
        has_room=lambda: True,
        **extra,
    )


def _briefing_message(db) -> Message:
    return (
        db.query(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.continuous.is_(True), Message.origin == "initiative")
        .one()
    )


def test_it_is_scheduled_when_quiet_hours_end_once_a_day(client, db):
    world(client, db)
    _login(client, db)
    owner = _owner(db)
    evening = datetime(2026, 11, 17, 23, 0, tzinfo=UTC)  # 20:00 in São Paulo

    briefing.ensure_scheduled(db, owner, evening)
    briefing.ensure_scheduled(db, owner, evening + timedelta(minutes=30))

    jobs = db.query(ScheduledJob).filter_by(kind=briefing.JOB_KIND).all()
    assert len(jobs) == 1 and jobs[0].run_after.replace(tzinfo=UTC) == MORNING
    owner.autonomy_permissions = {briefing.PERMISSION: False}
    db.commit()
    briefing.ensure_scheduled(db, owner, MORNING + timedelta(hours=1))
    assert db.query(ScheduledJob).filter_by(kind=briefing.JOB_KIND).count() == 1


def test_nothing_new_sends_nothing(client, db):
    llm, _, browser = world(client, db)
    _login(client, db)
    owner = _owner(db)
    report = _run(db, llm, browser, owner)
    assert (report.sent, report.reason) == (False, "nothing_new")
    assert db.query(Message).filter_by(origin="initiative").count() == 0


def test_the_panels_are_checked_now_and_the_briefing_says_it(client, db, monkeypatch):
    llm, _, browser = world(client, db)
    pushes = []
    monkeypatch.setattr(briefing.push, "send_to_owner", lambda *a, **k: pushes.append(k) or 1)
    monkeypatch.setattr(panels.push, "send_to_owner", lambda *a, **k: pushes.append(k) or 1)
    headers = _login(client, db)
    make_panel(client, db, headers)
    owner = _owner(db)
    panel = db.query(Panel).one()
    panel.checked_at = MORNING - timedelta(days=1)
    db.commit()
    _say(llm, "Bom dia! Quarta.\n- Combo Santiago: R$ 5.945, abaixo da meta de R$ 6.000.")

    report = _run(db, llm, browser, owner)

    assert report.sent and report.written_by == "model"
    assert "R$ 5.945" in _briefing_message(db).content
    # One notice for the morning, not one for the panel and another for the briefing.
    assert [p["title"] for p in pushes] == ["Bom dia"]
    db.refresh(panel)
    assert panel.goal_alerted_at is not None  # being below the goal was said
    asked = json.loads(llm.prompts[-1][1].content)["fatos"]["paineis"][0]
    assert asked["total"] == "R$ 5.945" and asked["abaixo_da_meta_agora"] is True
    # The 9h check was moved by this one: the job left for 9h does nothing.
    nine = [
        j
        for j in db.query(ScheduledJob).filter_by(kind=panels.JOB_KIND).all()
        if panels.stale(panel, j.payload.get("at"))
    ]
    assert nine


def test_a_sum_of_money_not_in_the_facts_is_refused(client, db, monkeypatch):
    llm, _, browser = world(client, db)
    monkeypatch.setattr(briefing.push, "send_to_owner", lambda *a, **k: 1)
    monkeypatch.setattr(panels.push, "send_to_owner", lambda *a, **k: 1)
    headers = _login(client, db)
    make_panel(client, db, headers)
    owner = _owner(db)
    _say(llm, "Bom dia! O Combo Santiago caiu para R$ 3.100.")

    report = _run(db, llm, browser, owner)

    assert report.written_by == "code"
    text = _briefing_message(db).content
    assert "R$ 3.100" not in text and text.startswith("Bom dia! Hoje é quarta, 18/11.")
    assert "Combo Santiago" in text


def test_paused_or_turned_off_it_stays_quiet(client, db):
    llm, _, browser = world(client, db)
    headers = _login(client, db)
    make_panel(client, db, headers)
    owner = _owner(db)
    owner.autonomy_permissions = {briefing.PERMISSION: False}
    db.commit()
    assert _run(db, llm, browser, owner).reason == "off"
    # Asked for in Settings, it goes even when the daily one is off.
    assert _run(db, llm, browser, owner, asked=True).reason in ("sent", "nothing_new")


def test_settings_turn_it_off_and_ask_for_one_now(client, db):
    world(client, db)
    headers = _login(client, db)

    assert client.get("/autonomy/permissions", headers=headers).json()["morning_briefing"] is True
    off = client.put(
        "/autonomy/permissions", headers=headers, json={"morning_briefing": False}
    ).json()
    assert off["morning_briefing"] is False and off["auto_research"] is False
    assert client.post("/autonomy/briefing", headers=headers).json() == {"queued": True}
    job = db.query(ScheduledJob).filter_by(kind=briefing.JOB_KIND).one()
    assert job.payload["asked"] is True


def test_the_manifest_says_when_it_comes():
    said = "; ".join(Capabilities(morning_briefing="08:00").actions())
    assert "todo dia às 08:00" in said and "resumo da manhã" in said
    assert "resumo da manhã" not in "; ".join(Capabilities().actions())


def test_a_broken_backup_is_said_even_with_nothing_else(client, db, tmp_path):
    llm, _, browser = world(client, db)
    _login(client, db)
    owner = _owner(db)
    (tmp_path / "last.json").write_text(
        json.dumps({"ok": False, "at": MORNING.isoformat(), "step": "dump"})
    )
    report = _run(db, llm, browser, owner, backup_dir=str(tmp_path))
    assert report.sent
    text = _briefing_message(db).content
    assert "falhou na etapa dump" in text  # the fake model answers no JSON: written in code
