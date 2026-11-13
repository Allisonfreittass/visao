"""Asking for Mac work in plain words: a cheap check in code, one short extraction, and a task
that only waits for the owner's tap; nothing the model inferred runs on its own."""

import json
from dataclasses import replace

from sqlalchemy import select

from core.arm.intent import PURPOSE, candidate
from core.decision.pipeline import run_turn
from core.identity.genesis import get_identity
from infrastructure.database.models import ArmTask, ModelUsage
from integrations.llm.base import ChatMessage
from tests.fakes import FakeLLMProvider
from tests.integration.test_mind import setup
from tests.integration.test_mind_temperament import chat, mac
from tests.integration.test_phase9 import CONFIG

PROJECTS = ["mercado", "visao"]


def test_only_a_named_project_or_the_mac_with_an_action_reaches_the_model():
    assert candidate("roda os testes do visao", PROJECTS)
    assert candidate("corrige o bug do login no mercado", PROJECTS)
    assert candidate("faz um build no meu mac", PROJECTS)
    assert not candidate("o que você acha do visao?", PROJECTS)
    assert not candidate("bom dia, tudo bem?", PROJECTS)
    assert not candidate(
        "/mac visao rode os testes", PROJECTS
    )  # the explicit command has its own path
    assert not candidate("roda os testes do visao", [])


def test_a_slash_mac_in_the_middle_of_a_sentence_is_a_request_too():
    assert candidate("Foi bom demais. Vamos testar algo. /mac git status", PROJECTS)
    assert not candidate("comprei um imac/macbook novo", PROJECTS)


def test_a_slash_mac_without_a_project_goes_to_the_only_one_and_waits_for_a_tap(db):
    owner = setup(db)
    mac(db, owner, ["visao"])
    outcome, _ = turn(
        db,
        owner,
        "Foi bom demais. Vamos testar algo. /mac git status",
        {"mac_task": True, "project": "", "task": "Rode git status e mostre a saída."},
    )
    task = db.scalar(select(ArmTask))
    assert (task.project, task.status) == ("visao", "proposed")
    assert "mac_proposed" in outcome.plan.executed()


def test_talk_about_the_mac_never_gets_a_no_connection_answer(db):
    owner = setup(db)
    mac(db, owner, PROJECTS)
    _, provider = turn(
        db, owner, "você está conectado no meu mac?", {"mac_task": False, "project": "", "task": ""}
    )
    system = provider.prompts[-1][0].content
    assert "está pareado com você" in system and "/mac mercado rode git status" in system
    assert db.scalar(select(ArmTask)) is None


def responder(extraction):
    def answer(messages: list[ChatMessage]) -> str:
        if '"mac_task"' in messages[0].content:
            return json.dumps(extraction, ensure_ascii=False)
        return "Vou pedir ao Mac para rodar os testes do visao assim que você aprovar."

    return answer


def turn(db, owner, text, extraction):
    provider = FakeLLMProvider(responder=responder(extraction))
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text=text,
        provider=provider,
        search=None,
        config=replace(CONFIG, curiosity_enabled=False),
    )
    return outcome, provider


def test_a_plain_request_becomes_a_task_that_waits_for_a_tap(db, monkeypatch):
    owner = setup(db)
    mac(db, owner, PROJECTS)
    pushed = []
    monkeypatch.setattr("core.arm.service.push.send_to_owner", lambda *a, **k: pushed.append(k))
    outcome, provider = turn(
        db,
        owner,
        "roda os testes do visao e me diz o que quebrou",
        {"mac_task": True, "project": "visao", "task": "Rode os testes e diga o que quebrou."},
    )
    task = db.scalar(select(ArmTask))
    assert task.status == "proposed" and task.requested_by == "agent"
    assert task.project == "visao" and task.conversation_id == chat(db, owner).id
    assert pushed == []  # the owner is in the conversation: no notification
    assert "mac_proposed" in outcome.plan.executed()
    system = provider.prompts[-1][0].content
    assert "esperando o toque da pessoa" in system and "nada rodou ainda" in system


def test_talk_about_a_project_is_not_a_task(db):
    owner = setup(db)
    mac(db, owner, PROJECTS)
    turn(
        db,
        owner,
        "você acha que vale refatorar o visao?",
        {"mac_task": False, "project": "", "task": ""},
    )
    assert db.scalar(select(ArmTask)) is None
    assert db.scalar(select(ModelUsage).where(ModelUsage.purpose == PURPOSE)).outcome == "no_task"


def test_a_project_the_mac_does_not_allow_is_never_proposed(db):
    owner = setup(db)
    mac(db, owner, PROJECTS)
    turn(
        db,
        owner,
        "roda os testes do visao",
        {"mac_task": True, "project": "outro", "task": "rode tudo"},
    )
    assert db.scalar(select(ArmTask)) is None


def test_without_a_paired_mac_there_is_no_extra_call(db):
    owner = setup(db)
    _, provider = turn(
        db, owner, "roda os testes do visao", {"mac_task": True, "project": "visao", "task": "x"}
    )
    assert not any('"mac_task"' in p[0].content for p in provider.prompts)
    assert db.scalar(select(ArmTask)) is None
