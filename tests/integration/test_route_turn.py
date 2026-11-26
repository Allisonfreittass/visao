"""The source chosen by the model when no word list caught the message (core/decision/route.py).

The conversation of 25/11/2026, as it happened: "Cara, uma dúvida, quantos commits meus foram
feitos hoje?", then "pode ver o do visao", then "Isso mesmo". None reached GitHub; the reply
searched the web for "git log". Now the follow-up is written whole and goes the GitHub path."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from core.decision import route
from core.decision.pipeline import run_turn
from core.identity.genesis import get_identity
from tests.fakes import FakeLLMProvider
from tests.integration.test_github_turn import github
from tests.integration.test_mind import setup
from tests.integration.test_mind_temperament import chat, say
from tests.integration.test_phase9 import CONFIG

QUIET = replace(CONFIG, curiosity_enabled=False)


def answering(routed: dict | str | None, reply: str = "Hoje foram 3 commits no visao."):
    def answer(messages):
        if messages[0].content == route.INSTRUCTIONS:
            return routed if isinstance(routed, str) else json.dumps(routed)
        return reply

    return FakeLLMProvider(responder=answer)


def routing_calls(provider) -> list[dict]:
    return [
        json.loads(p[1].content) for p in provider.prompts if p[0].content == route.INSTRUCTIONS
    ]


def the_commits_conversation(db, owner):
    now = datetime.now(UTC)
    say(
        db,
        owner,
        "user",
        "Cara, uma dúvida, quantos commits meus foram feitos hoje?",
        now - timedelta(minutes=3),
    )
    say(
        db,
        owner,
        "assistant",
        "Não consigo ver seus commits no GitHub daqui ainda. Qual repositório?",
        now - timedelta(minutes=2),
    )
    say(db, owner, "user", "pode ver o do visao", now - timedelta(minutes=1))
    say(
        db,
        owner,
        "assistant",
        "Quantos commits foram feitos hoje no repositório Visao?",
        now - timedelta(seconds=50),
    )


def turn(db, owner, text, provider, *, config=QUIET, gh=None, modality="text"):
    return run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text=text,
        provider=provider,
        search=None,
        config=config,
        github=gh,
        modality=modality,
    )


def test_isso_mesmo_after_the_commits_question_reads_github(db):
    owner = setup(db)
    the_commits_conversation(db, owner)
    provider = answering(
        {"fonte": "github", "pedido": "quantos commits o repositório visao teve hoje?"}
    )
    outcome = turn(db, owner, "Isso mesmo", provider, gh=github(3))
    executed = outcome.plan.executed()
    assert "routed" in executed and "github_read" in executed
    # The call saw what is on and the turns before it.
    [asked] = routing_calls(provider)
    assert asked["fontes"] == {"github": True}
    assert "quantos commits meus foram feitos hoje" in asked["conversa_recente"]
    assert asked["mensagem"] == "Isso mesmo"
    # The number reached the reply as data.
    assert ": 3." in provider.prompts[-1][0].content


def test_a_message_the_word_lists_catch_costs_no_routing_call(db):
    owner = setup(db)
    provider = answering({"fonte": "github", "pedido": "x"})
    outcome = turn(db, owner, "quantos commits teve hoje no visao?", provider, gh=github(3))
    assert "github_read" in outcome.plan.executed()
    assert routing_calls(provider) == []


def test_social_voice_commands_and_nothing_on_skip_the_call(db):
    owner = setup(db)
    the_commits_conversation(db, owner)
    for text, kwargs in [
        ("valeu, cara!", {"gh": github(0)}),
        ("Isso mesmo", {"gh": github(0), "modality": "voice"}),
        ("/ajuda", {"gh": github(0)}),
        ("Isso mesmo", {"gh": None}),  # no GitHub, no Google, no apps: nothing to choose
    ]:
        provider = answering({"fonte": "github", "pedido": "x"})
        outcome = turn(db, owner, text, provider, **kwargs)
        assert routing_calls(provider) == [], text
        assert "routed" not in outcome.plan.executed(), text


def test_general_questions_stay_out_of_the_owners_data(db):
    owner = setup(db)
    provider = answering({"fonte": None, "pedido": "como funciona o git rebase?"})
    outcome = turn(db, owner, "como funciona o git rebase?", provider, gh=github(0))
    assert len(routing_calls(provider)) == 1
    executed = outcome.plan.executed()
    assert "routed" not in executed and not any(a.startswith("github") for a in executed)


def test_an_answer_outside_what_is_on_opens_nothing(db):
    owner = setup(db)
    for answer in (
        {"fonte": "google", "pedido": "tenho reunião amanhã?"},  # Google not connected here
        {"fonte": "apps", "pedido": "minhas páginas", "app": "Notion"},  # no app connected
        {"fonte": "terminal", "pedido": "rm -rf"},
        "não sei",
    ):
        provider = answering(answer)
        outcome = turn(db, owner, "e aquilo de ontem?", provider, gh=github(0))
        assert "routed" not in outcome.plan.executed(), answer


def test_an_app_that_is_not_connected_says_where_to_connect_and_never_searches(db):
    owner = setup(db)
    provider = answering(
        {"fonte": "nao_conectado", "pedido": "o que tem no meu Notion?", "app": "Notion"},
        reply="Conecta o Notion em Ajustes que eu olho.",
    )
    outcome = turn(
        db,
        owner,
        "e o que tá lá nas minhas anotações do trampo?",
        provider,
        config=CONFIG,
        gh=github(0),
    )
    executed = outcome.plan.executed()
    assert "routed" in executed and "research" not in executed
    system = provider.prompts[-1][0].content
    assert "Notion, que não está conectado" in system and "Ajustes › Integrações › Apps" in system


def test_without_budget_the_word_lists_decide_alone(db, monkeypatch):
    owner = setup(db)

    def spent(*_args, **_kwargs):
        raise route.BudgetExceededError("daily", 1, 1)

    monkeypatch.setattr(route, "check_budgets", spent)
    provider = answering({"fonte": "github", "pedido": "x"})
    outcome = turn(db, owner, "Isso mesmo", provider, gh=github(0))
    assert routing_calls(provider) == []
    assert "routed" not in outcome.plan.executed()


def test_social_and_worth_asking():
    on = {"github": True}
    for text in ("valeu", "Obrigado!", "bom dia, cara", "kkkkk", "tudo bem?"):
        assert route.social(text), text
    for text in ("sim", "ok", "beleza", "Isso mesmo", "pode ver o do visao"):
        assert not route.social(text), text
    assert route.worth_asking("Isso mesmo", voice=False, sources=on)
    assert not route.worth_asking("Isso mesmo", voice=True, sources=on)
    assert not route.worth_asking("Isso mesmo", voice=False, sources={"github": False, "apps": ()})
    assert not route.worth_asking("/mac visao git status", voice=False, sources=on)


def test_a_follow_up_about_a_connected_app_reaches_it(db, monkeypatch):
    import pytest

    pytest.importorskip("composio")
    from core.apps import account, assist
    from integrations.composio.client import ComposioClient
    from tests.fake_composio import RecordedComposio
    from tests.integration.test_apps_assist import KEY, LIST

    recorded = RecordedComposio()
    recorded.connected()
    account._CONNECTED.clear()
    client = ComposioClient("chave-composio", http=recorded.http())
    monkeypatch.setattr(account, "client", lambda key: client if key == "ck_test" else None)

    owner = setup(db)
    now = datetime.now(UTC)
    say(db, owner, "user", "tem coisa aberta lá no visao?", now - timedelta(minutes=1))

    def answer(messages):
        system = messages[0].content
        if system == route.INSTRUCTIONS:
            return json.dumps(
                {"fonte": "apps", "pedido": "quais issues estão abertas no visao", "app": "GitHub"}
            )
        if system == assist.TOOL_INSTRUCTIONS:
            return json.dumps({"calls": [LIST]})
        return "Tem uma aberta."

    provider = FakeLLMProvider(responder=answer)
    config = replace(QUIET, google_secret=KEY, apps_key="ck_test")
    outcome = turn(db, owner, "e as que tão pendentes?", provider, config=config)
    executed = outcome.plan.executed()
    assert "routed" in executed and "apps_read" in executed
    assert routing_calls(provider)[0]["fontes"]["apps"] == ["GitHub"]
