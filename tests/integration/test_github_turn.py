"""25/11/2026: "Quantos commits foram feitos hoje no repositório Visao?" became a Mac task that
never ran with the Mac off. GitHub is read on the server now: the number reaches the reply in the
same turn, with no question back and no Mac."""

from dataclasses import replace
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from core.decision.pipeline import run_turn
from core.identity.genesis import get_identity
from infrastructure.database.models import ArmTask
from integrations.github.api import GitHubAPI
from tests.fakes import FakeLLMProvider
from tests.integration.test_mind import setup
from tests.integration.test_mind_temperament import chat, mac
from tests.integration.test_phase9 import CONFIG


def github(count: int) -> GitHubAPI:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/Allisonfreittass/visao/commits"
        return httpx.Response(
            200,
            json=[
                {
                    "sha": f"{i:07d}ff",
                    "commit": {
                        "message": f"Commit {i}",
                        "author": {"date": datetime.now(UTC).isoformat()},
                    },
                }
                for i in range(count)
            ],
        )

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    return GitHubAPI("tok", client=client)


def test_commits_today_with_the_mac_off_come_from_the_server(db):
    owner = setup(db)
    mac(db, owner, ["visao"])  # paired, last seen long ago: off
    provider = FakeLLMProvider(reply_text="Hoje foram 3 commits no visao.")
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="quantos commits teve hoje no visao?",
        provider=provider,
        search=None,
        config=CONFIG,
        github=github(3),
    )
    assert "github_read" in outcome.plan.executed()
    assert db.scalar(select(ArmTask)) is None
    # One model call: the reply. No Mac extraction, no curiosity assessment in between.
    assert len(provider.prompts) == 1
    system = provider.prompts[0][0].content
    assert "Commits em Allisonfreittass/visao (branch principal) hoje" in system
    assert ": 3." in system and "sem perguntar qual repositório" in system


def test_a_message_without_github_never_reads_it(db):
    owner = setup(db)
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="bom dia",
        provider=FakeLLMProvider(),
        search=None,
        config=replace(CONFIG, curiosity_enabled=False),
        github=github(0),
    )
    assert not any(a.startswith("github") for a in outcome.plan.executed())


def test_a_mac_request_with_the_mac_off_gets_one_short_sentence(db):
    owner = setup(db)
    mac(db, owner, ["visao"])  # off
    extraction = {"mac_task": True, "project": "visao", "task": "Rode os testes do visao."}

    def answer(messages):
        if '"mac_task"' in messages[0].content:
            import json

            return json.dumps(extraction)
        return "Seu Mac está desligado agora."

    provider = FakeLLMProvider(responder=answer)
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="roda os testes do visao",
        provider=provider,
        search=None,
        config=replace(CONFIG, curiosity_enabled=False),
        github=github(0),
    )
    assert db.scalar(select(ArmTask)) is None
    assert any(a["action"] == "mac_blocked" for a in outcome.plan.actions)
    system = provider.prompts[-1][0].content
    assert "Seu Mac está desligado agora" in system and "Nada foi pedido ao Mac" in system


def test_owner_data_without_a_tool_is_never_searched_on_the_web(db):
    owner = setup(db)
    provider = FakeLLMProvider(reply_text="Não tenho acesso ao seu e-mail.")
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="tem algo importante nos meus e-mails hoje?",
        provider=provider,
        search=None,
        config=CONFIG,  # curiosity on: it would have assessed and maybe searched
    )
    assert any(a["action"] == "owner_data_missing" for a in outcome.plan.actions)
    assert len(provider.prompts) == 1  # no curiosity assessment, no research
    assert "precisa conectar o Google em Ajustes" in provider.prompts[0][0].content


def test_a_reply_that_echoes_the_question_is_written_again(db):
    owner = setup(db)
    drafts = iter(["Você quer saber quantos commits teve hoje no visao?", "Hoje foram 3 commits."])
    provider = FakeLLMProvider(responder=lambda messages: next(drafts))
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="quantos commits teve hoje no visao?",
        provider=provider,
        search=None,
        config=CONFIG,
        github=github(3),
    )
    assert outcome.result.assistant_message.content == "Hoje foram 3 commits."
    assert "só devolveu a pergunta" in provider.prompts[-1][-1].content


def test_a_reply_that_denies_the_github_read_is_replaced_by_the_numbers(db):
    owner = setup(db)
    # A small model copying an earlier reply instead of the data it was given (25/11/2026).
    provider = FakeLLMProvider(
        reply_text="Não, não abri o GitHub do Visao e o Mac continua desligado, então não tenho "
        "esse número."
    )
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="quantos commits teve hoje no visao?",
        provider=provider,
        search=None,
        config=replace(CONFIG, curiosity_enabled=False),
        github=github(42),
    )
    content = outcome.result.assistant_message.content
    assert content.startswith("Hoje foram 42 commits no Allisonfreittass/visao")
    assert "não abri" not in content and "desligado" not in content
    assert "github_denial_fixed" in outcome.plan.executed()


def test_the_mac_on_is_never_called_off(db):
    owner = setup(db)
    device = mac(db, owner, ["visao"])
    device.last_seen_at = datetime.now(UTC)
    db.commit()
    provider = FakeLLMProvider(
        reply_text="Sou pareado com o seu Mac, sim. O Mac está desligado. Use /mac visao rode git "
        "status."
    )
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="você está conectado ao meu pc né?",
        provider=provider,
        search=None,
        config=replace(CONFIG, curiosity_enabled=False),
    )
    content = outcome.result.assistant_message.content
    assert "desligado" not in content and "Seu Mac está ligado agora" in content
    assert content.startswith("Sou pareado com o seu Mac, sim.")
    assert "mac_off_fixed" in outcome.plan.executed()


def test_how_was_my_day_is_built_on_what_was_measured(db):
    owner = setup(db)
    # The model still says it does not know: code puts the measured day in its place.
    provider = FakeLLMProvider(reply_text="Não sei como foi seu dia; você ainda não me contou.")
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="E aí, como foi meu dia hoje?",
        provider=provider,
        search=None,
        config=CONFIG,
        github=github(3),
    )
    system = provider.prompts[0][0].content
    assert "O dia do dono hoje" in system and "Commits hoje em Allisonfreittass/visao: 3." in system
    assert len(provider.prompts) == 1  # no curiosity question in between
    content = outcome.result.assistant_message.content
    assert content.startswith("Hoje foram 3 commits no visao")
    assert "day_denial_fixed" in outcome.plan.executed()


def test_hold_me_to_it_records_the_follow_up_with_its_hour(db):
    from infrastructure.database.models import Intention

    owner = setup(db)
    provider = FakeLLMProvider(reply_text="Fechado, te cobro sexta às 17h.")
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="me cobra: eu disse que ia terminar o painel de preços essa semana",
        provider=provider,
        search=None,
        config=replace(CONFIG, mind_enabled=True, curiosity_enabled=False),
    )
    intention = db.scalar(select(Intention))
    assert intention is not None and "painel de preços" in intention.about
    assert "followup_recorded" in outcome.plan.executed()
    system = provider.prompts[-1][0].content
    assert "A cobrança foi registrada agora pelo sistema" in system


def test_without_the_mind_it_never_promises_to_follow_up(db):
    owner = setup(db)
    provider = FakeLLMProvider()
    run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="me cobra o painel essa semana",
        provider=provider,
        search=None,
        config=replace(CONFIG, mind_enabled=False, curiosity_enabled=False),
    )
    assert "não prometa cobrar" in provider.prompts[-1][0].content
