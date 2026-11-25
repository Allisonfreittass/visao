"""Habilidades: the owner lists and switches the skills, and a switched-on skill reaches the reply
that asks for it."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from core.decision.pipeline import run_turn
from core.identity.genesis import get_identity
from infrastructure.database.models import AuditLog, Decision
from tests.fakes import FakeLLMProvider
from tests.integration.test_mind import _owner_client, setup
from tests.integration.test_mind_temperament import chat, say
from tests.integration.test_phase9 import CONFIG

BUG_LINE = "Regra de ferro: nenhum conserto sem investigar a causa antes."


def test_the_owner_lists_and_switches_the_skills(client, db):
    owner, headers = _owner_client(client, db)
    listed = client.get("/skills", headers=headers).json()["skills"]
    assert len(listed) == 5
    assert all(s["enabled"] and s["origin"] == "instalada" for s in listed)
    bugs = next(s for s in listed if s["id"] == "achar-bugs")
    assert bugs["source"] == "obra/superpowers" and bugs["license"] == "MIT"

    off = client.put("/skills/achar-bugs", json={"enabled": False}, headers=headers).json()
    assert off["enabled"] is False
    again = {s["id"]: s["enabled"] for s in client.get("/skills", headers=headers).json()["skills"]}
    assert again["achar-bugs"] is False and again["ideias"] is True
    assert client.put("/skills/achar-bugs", json={"enabled": True}, headers=headers).json()[
        "enabled"
    ]
    toggles = db.query(AuditLog).filter(AuditLog.action == "skill.toggle").count()
    assert toggles == 2


def test_an_unknown_skill_and_no_login_are_refused(client, db):
    _, headers = _owner_client(client, db)
    assert client.put("/skills/nada", json={"enabled": True}, headers=headers).status_code == 404
    assert client.get("/skills").status_code == 401


def _turn(db, owner, text):
    provider = FakeLLMProvider(reply_text="Vamos achar a causa.")
    run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text=text,
        provider=provider,
        search=None,
        config=replace(CONFIG, curiosity_enabled=False),
    )
    return provider.prompts[-1][0].content


def test_a_switched_on_skill_reaches_the_reply_that_asks_for_it(db):
    owner = setup(db)
    prompt = _turn(db, owner, "o deploy falhou de novo, deu erro no build")
    assert BUG_LINE in prompt
    manifest = next(line for line in prompt.splitlines() if "seguir as habilidades ligadas" in line)
    assert "Achar a causa de um bug" in manifest  # it knows what is on
    decision = db.query(Decision).order_by(Decision.created_at.desc()).first()
    assert any(a.get("skill") == "achar-bugs" for a in decision.actions)


def test_a_switched_off_skill_stays_out(db):
    from core.skills import catalog

    owner = setup(db)
    catalog.set_enabled(db, catalog.by_id("achar-bugs"), False, actor_user_id=owner.id)
    db.commit()
    prompt = _turn(db, owner, "o deploy falhou de novo, deu erro no build")
    assert BUG_LINE not in prompt
    manifest = next(line for line in prompt.splitlines() if "seguir as habilidades ligadas" in line)
    assert "Achar a causa de um bug" not in manifest and "Design de telas" in manifest


def test_a_skill_follows_the_next_replies(db):
    owner = setup(db)
    say(db, owner, "user", "deu erro no build do app", datetime.now(UTC) - timedelta(minutes=10))
    assert BUG_LINE in _turn(db, owner, "aqui o log que você pediu")


def test_a_skill_does_not_follow_into_the_next_day(db):
    owner = setup(db)
    say(db, owner, "user", "deu erro no build do app", datetime.now(UTC) - timedelta(days=1))
    assert BUG_LINE not in _turn(db, owner, "bom dia")
