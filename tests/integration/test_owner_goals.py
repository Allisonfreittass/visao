"""The owner's goals, written only with the owner's yes (docs/decisions/0025)."""

import json

from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core import actions, owner_goals
from core.identity.genesis import run_genesis
from infrastructure.database.models import OwnerGoal, PendingAction
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login

ASKED_GOAL = "Quer que eu registre isso como uma mudança nos seus objetivos?"


def world(client, db, *, actions_answer=None, replies=None):
    """Actions from `actions_answer`, one list per action call; replies from `replies`, one per
    chat turn. Everything else (curation, review) gets an empty JSON."""
    answers = list(actions_answer or [])
    said = list(replies or [])
    llm = FakeLLMProvider(
        responder=lambda messages: (
            json.dumps({"actions": answers.pop(0) if answers else []})
            if messages[0].content == actions.INSTRUCTIONS
            else (said.pop(0) if said else "Certo.")
            if "Objetivos que essa pessoa" in messages[0].content
            else "{}"
        )
    )
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm


def _owner(client, db, *, memory=True):
    headers = _login(client, db)
    client.put("/memory/settings", headers=headers, json={"enabled": memory})
    conversation = client.get("/conversations/continuous", headers=headers).json()["id"]
    return headers, conversation


def _send(client, headers, conversation, text):
    response = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": text}
    )
    assert response.status_code == 200, response.text
    return response.json()["assistant_message"]["content"]


def _chat_prompt(llm):
    return next(p for p in reversed(llm.prompts) if "Objetivos que essa pessoa" in p[0].content)[
        0
    ].content


def _goals(client, headers):
    return client.get("/owner-goals", headers=headers).json()


def test_the_day_with_visao_registers_the_goal_only_after_the_yes(client, db):
    llm = world(
        client,
        db,
        actions_answer=[
            [
                {
                    "do": "set_goal",
                    "goal": "construir um produto próprio",
                    "reason": "quer algo dele, não mais prestar serviços",
                }
            ]
        ],
        replies=[
            "Lembro que você começou aquele projeto para reduzir o trabalho manual dos clientes. "
            "O que mudou na sua percepção desde então?",
            "Isso se conecta com o que você vem dizendo: um produto próprio. " + ASKED_GOAL,
            "Registrado.",
        ],
    )
    headers, conversation = _owner(client, db)

    _send(client, headers, conversation, "Estou pensando em abandonar meu projeto de automação.")
    second = "Acho que estou mais interessado em construir algo meu do que prestar serviços."
    _send(client, headers, conversation, second)
    # Said, but not asked to write down: nothing yet, and the reply asked.
    assert _goals(client, headers)["active"] == []
    assert "pergunte em uma frase se pode registrar" in _chat_prompt(llm)

    _send(client, headers, conversation, "sim")

    [goal] = _goals(client, headers)["active"]
    assert goal["content"] == "construir um produto próprio"
    assert goal["source_text"] == second  # the owner's words, not the "sim"
    assert goal["source_message_id"] is not None
    assert "registrei o objetivo «construir um produto próprio»" in _chat_prompt(llm)

    _send(client, headers, conversation, "e agora?")
    assert "- construir um produto próprio (desde" in _chat_prompt(llm)


def test_without_the_yes_it_waits_and_a_no_drops_it(client, db):
    llm = world(
        client,
        db,
        actions_answer=[
            [{"do": "set_goal", "goal": "vender o app", "reason": "quer viver dele"}],
        ],
        replies=["Posso registrar «vender o app» como objetivo seu?", "Tudo bem, não registro."],
    )
    headers, conversation = _owner(client, db)

    _send(client, headers, conversation, "meu objetivo agora é vender o app, cria o projeto Venda")
    assert _goals(client, headers)["active"] == []
    assert db.query(PendingAction).one().kind == "set_goal"
    assert "registrar o objetivo «vender o app»: espera o sim dela" in _chat_prompt(llm)

    _send(client, headers, conversation, "não")
    assert _goals(client, headers)["active"] == []
    assert db.query(PendingAction).one().status == "dropped"


def test_a_yes_to_the_waiting_goal_writes_it(client, db):
    world(
        client,
        db,
        actions_answer=[[{"do": "set_goal", "goal": "vender o app", "reason": ""}]],
        replies=["Posso registrar?", "Pronto."],
    )
    headers, conversation = _owner(client, db)
    _send(client, headers, conversation, "meu objetivo agora é vender o app, cria o projeto Venda")
    _send(client, headers, conversation, "sim")
    assert [g["content"] for g in _goals(client, headers)["active"]] == ["vender o app"]


def test_asking_in_so_many_words_is_the_yes(client, db):
    world(
        client,
        db,
        actions_answer=[[{"do": "set_goal", "goal": "terminar o curso de Go"}]],
    )
    headers, conversation = _owner(client, db)
    _send(client, headers, conversation, "registra como objetivo meu terminar o curso de Go")
    assert [g["content"] for g in _goals(client, headers)["active"]] == ["terminar o curso de Go"]
    assert db.query(PendingAction).count() == 0


def test_with_memory_off_nothing_is_written(client, db):
    llm = world(
        client,
        db,
        actions_answer=[[{"do": "set_goal", "goal": "terminar o curso de Go"}]],
    )
    headers, conversation = _owner(client, db, memory=False)
    _send(client, headers, conversation, "registra como objetivo meu terminar o curso de Go")
    assert db.query(OwnerGoal).count() == 0
    # With memory off the goals block is not in the prompt: the deed says why in the actions.
    assert not any("registrei o objetivo" in p[0].content for p in llm.prompts)


def test_a_change_replaces_and_undo_brings_the_old_goal_back(client, db):
    world(
        client,
        db,
        actions_answer=[
            [{"do": "set_goal", "goal": "crescer a agência de automação"}],
            [
                {
                    "do": "set_goal",
                    "goal": "construir um produto próprio",
                    "replaces": "crescer a agência de automação",
                }
            ],
        ],
    )
    headers, conversation = _owner(client, db)
    _send(client, headers, conversation, "registra como objetivo meu crescer a agência")
    _send(client, headers, conversation, "atualiza meu objetivo: construir um produto próprio")

    goals = _goals(client, headers)
    assert [g["content"] for g in goals["active"]] == ["construir um produto próprio"]
    old = next(g for g in goals["history"] if g["content"] == "crescer a agência de automação")
    assert old["status"] == "ended"

    undo = client.post("/owner-goals/undo", headers=headers).json()
    assert "voltou «crescer a agência de automação»" in undo["undone"]
    assert [g["content"] for g in _goals(client, headers)["active"]] == [
        "crescer a agência de automação"
    ]
    client.post("/owner-goals/undo", headers=headers)
    assert _goals(client, headers)["active"] == []
    assert client.post("/owner-goals/undo", headers=headers).json() == {"undone": None}


def test_it_never_says_it_registered_when_it_did_not(client, db):
    world(client, db, replies=["Registrei isso nos seus objetivos. Bom caminho."])
    headers, conversation = _owner(client, db)
    reply = _send(client, headers, conversation, "quero construir algo meu")
    assert "Registrei" not in reply
    assert db.query(OwnerGoal).count() == 0


def test_forgetting_everything_takes_the_goals_too(client, db):
    world(client, db, actions_answer=[[{"do": "set_goal", "goal": "terminar o curso de Go"}]])
    headers, conversation = _owner(client, db)
    _send(client, headers, conversation, "registra como objetivo meu terminar o curso de Go")
    assert db.query(OwnerGoal).count() == 1
    client.delete("/memory", headers=headers)
    assert db.query(OwnerGoal).count() == 0


def test_the_goals_are_private(client, db):
    world(client, db, actions_answer=[[{"do": "set_goal", "goal": "terminar o curso de Go"}]])
    headers, conversation = _owner(client, db)
    _send(client, headers, conversation, "registra como objetivo meu terminar o curso de Go")
    other = _login(client, db, "b@exemplo.com")
    assert client.get("/owner-goals", headers=other).json() == {"active": [], "history": []}
    assert client.post("/owner-goals/undo", headers=other).json() == {"undone": None}
    assert _goals(client, headers)["active"][0]["status"] == "active"


def test_only_a_request_or_a_yes_to_the_question_counts():
    assert owner_goals.consent("registra como objetivo meu vender o app", "").given
    assert owner_goals.consent("tira esse objetivo", "").given
    assert not owner_goals.consent("estou pensando em mudar meu objetivo", "").given
    assert not owner_goals.consent("meu objetivo é vender o app", "").given
    yes = owner_goals.consent("sim", ASKED_GOAL)
    assert yes.given and yes.by_yes
    assert not owner_goals.consent("sim", "Quer que eu anote no projeto?").given
    assert not owner_goals.consent("talvez", ASKED_GOAL).given
    assert not owner_goals.consent("sim", "Registrei seus objetivos.").given  # no question
