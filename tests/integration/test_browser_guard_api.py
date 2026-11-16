"""With the browser there, a reply never denies it (docs/decisions/0013): the reply is checked in
code after it is written, rewritten by the same short check as the owner's rules, and what still
denies loses the sentence. The stream shows the kept text through the same `replace`."""

import json

from apps.api.browser import get_browser
from core import browse
from core.identity.system_prompt import RULE_CHECK_INSTRUCTIONS
from tests.integration.test_browse_api import (  # noqa: F401 - offline is an autouse fixture
    _actions,
    _chat_prompt,
    _send,
    offline,
    world,
)
from tests.integration.test_curiosity_api import _login
from tests.integration.test_stream_api import read, text_of
from tests.unit.test_browser_guard import AT_1135, AT_1137

KEPT_1137 = (
    "Depende da agência e do centro, mas aula costuma ser um custo a mais relevante. Em geral, "
    "cada aula de meio dia ou de dia inteiro é cobrada à parte, e o valor varia conforme o centro "
    "e a época."
)


def answers(llm, *, plan, reply, check):
    """The planner gets `plan`, the reply is `reply`, the rule check answers `check`."""

    def respond(messages):
        if messages[0].content == browse.INSTRUCTIONS:
            return json.dumps(plan)
        if messages[0].content == RULE_CHECK_INSTRUCTIONS:
            return json.dumps(check)
        return reply

    llm.responder = respond


def _guard_actions(db):
    return [a["reason"] for a in _actions(db) if a["action"] == "browser_denial_fixed"]


def test_the_1137_reply_is_rewritten_by_the_check(client, db):
    llm, _ = world(client, db, plan={}, pages={})
    answers(
        llm,
        plan={"browse": False, "missing": []},
        reply=AT_1137,
        check={"obeys": False, "rewrite": KEPT_1137},
    )
    headers = _login(client, db)

    _, turn = _send(client, headers, "o preço sobe muito se eu pegar aulas de esqui?")

    assert turn["assistant_message"]["content"] == KEPT_1137
    assert _guard_actions(db) == ["rewritten"]
    check = next(p for p in llm.prompts if p[0].content == RULE_CHECK_INSTRUCTIONS)
    assert "navegador de verdade está disponível" in json.loads(check[1].content)["regras"]


def test_when_the_check_says_it_obeys_the_sentence_goes_anyway(client, db):
    llm, _ = world(client, db, plan={}, pages={})
    answers(llm, plan={"browse": False, "missing": []}, reply=AT_1137, check={"obeys": True})
    headers = _login(client, db)

    _, turn = _send(client, headers, "o preço sobe muito se eu pegar aulas de esqui?")

    content = turn["assistant_message"]["content"]
    assert "não tenho preços atuais" not in content
    assert (
        content == f"{KEPT_1137} Consigo ver os preços de agora nos sites, num navegador de "
        "verdade: quer que eu olhe?"
    )
    assert _guard_actions(db) == ["stripped"]


def test_the_1135_reply_asks_for_what_is_missing_instead(client, db):
    llm, _ = world(client, db, plan={}, pages={})
    answers(
        llm,
        plan={"browse": False, "missing": ["cidade de saída"]},
        reply=AT_1135,
        check={"obeys": True},
    )
    headers = _login(client, db)

    _, turn = _send(client, headers, "quero ver passagem pra Santiago em agosto, 10 dias lá")

    content = turn["assistant_message"]["content"]
    assert "pedir à agência" not in content and "pesquisar nos sites" not in content
    assert content.endswith(
        "Consigo ver os preços de agora nos sites; para buscar, me diz cidade de saída?"
    )


def test_a_rewrite_that_still_denies_is_not_trusted(client, db):
    llm, _ = world(client, db, plan={}, pages={})
    still = "Aula é cobrada à parte. Não consigo consultar os preços ao vivo."
    answers(
        llm,
        plan={"browse": True, "urls": ["https://valle.cl/aulas"]},
        reply=AT_1137,
        check={"obeys": False, "rewrite": still},
    )
    headers = _login(client, db)

    _, turn = _send(client, headers, "o preço sobe muito se eu pegar aulas de esqui?")

    content = turn["assistant_message"]["content"]
    assert content == (
        "Aula é cobrada à parte. Tentei ver os preços ao vivo agora e não consegui; posso tentar "
        "de novo."
    )


def test_the_stream_ends_with_the_kept_text(client, db):
    llm, _ = world(client, db, plan={}, pages={})
    answers(llm, plan={"browse": False, "missing": []}, reply=AT_1137, check={"obeys": True})
    headers = _login(client, db)
    conversation, turn = _send(client, headers, "o preço sobe muito se eu pegar aulas de esqui?")

    events = read(client, headers, conversation, last=0)

    assert text_of(events) == turn["assistant_message"]["content"]
    assert "não tenho preços atuais" not in text_of(events)


def test_without_a_browser_the_reply_is_left_alone(client, db):
    llm, _ = world(client, db, plan={}, pages={})
    answers(llm, plan={}, reply=AT_1137, check={"obeys": True})
    client.app.dependency_overrides[get_browser] = lambda: None
    headers = _login(client, db)

    _, turn = _send(client, headers, "o preço sobe muito se eu pegar aulas de esqui?")

    assert turn["assistant_message"]["content"] == AT_1137
    assert all(p[0].content != RULE_CHECK_INSTRUCTIONS for p in llm.prompts)
    assert _guard_actions(db) == []


def test_a_reply_that_does_not_deny_costs_no_check(client, db):
    llm, _ = world(client, db, plan={}, pages={})
    answers(
        llm,
        plan={"browse": False, "missing": []},
        reply="Ficar em Santiago facilita a logística e dá para fazer bate-volta.",
        check={"obeys": True},
    )
    headers = _login(client, db)
    _send(client, headers, "acho melhor ficar em Santiago, o que acha do preço?")
    assert all(p[0].content != RULE_CHECK_INSTRUCTIONS for p in llm.prompts)
    assert _chat_prompt(llm)
