""" "Olhar sozinho" for the owner's apps (core/apps/glance.py): the read is chosen once, from the
read tools only, and then runs as it is every few hours, within the Composio month, into the mind
as third-party text."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from core.apps import account, glance
from integrations.composio.client import ComposioClient
from tests.fake_composio import API, RecordedComposio
from tests.fakes import FakeLLMProvider
from tests.integration.test_mind import setup

pytest.importorskip("composio")

KEY = "chave-de-teste-com-mais-de-32-caracteres!!"
EXECUTE = f"{API}/tools/execute/GITHUB_LIST_REPOSITORY_ISSUES"


@pytest.fixture
def api(monkeypatch):
    recorded = RecordedComposio()
    recorded.connected()
    account._CONNECTED.clear()
    glance._seen.clear()
    client = ComposioClient("chave-composio", http=recorded.http())
    monkeypatch.setattr(account, "client", lambda key: client if key == "ck_test" else None)
    return recorded, client


def picks(tool: str | None, arguments: dict | None = None) -> FakeLLMProvider:
    return FakeLLMProvider(reply_text=json.dumps({"tool": tool, "arguments": arguments or {}}))


def turn_on(db, owner, client, provider):
    return glance.choose(
        db, owner, provider=provider, apps=client, toolkit="github", app_name="GitHub"
    )


def executions(recorded) -> int:
    return len([r for r in recorded.requests if r.method == "POST" and r.url.path == EXECUTE])


def test_turning_it_on_picks_one_read_and_keeps_it(db, api):
    _, client = api
    owner = setup(db)
    provider = picks("GITHUB_LIST_REPOSITORY_ISSUES", {"owner": "dono", "repo": "visao"})
    choice = turn_on(db, owner, client, provider)
    assert choice.tool == "GITHUB_LIST_REPOSITORY_ISSUES"
    kept = glance.chosen(owner)["github"]
    assert kept["arguments"] == {"owner": "dono", "repo": "visao"} and kept["name"]
    # Only read tools reached the model: nothing that writes was even offered.
    offered = {t["slug"] for t in json.loads(provider.prompts[0][1].content)["tools"]}
    assert "GITHUB_LIST_REPOSITORY_ISSUES" in offered
    assert "GITHUB_CREATE_AN_ISSUE" not in offered and "GITHUB_UPDATE_AN_ISSUE" not in offered


@pytest.mark.parametrize("answer", ["GITHUB_CREATE_AN_ISSUE", "GITHUB_NAO_EXISTE", None])
def test_a_choice_that_writes_or_is_not_in_the_list_is_refused(db, api, answer):
    _, client = api
    owner = setup(db)
    with pytest.raises(glance.GlanceError):
        turn_on(db, owner, client, picks(answer))
    assert glance.chosen(owner) == {}


def test_without_a_model_it_says_so(db, api):
    _, client = api
    owner = setup(db)
    with pytest.raises(glance.GlanceError, match="Sem modelo"):
        turn_on(db, owner, client, None)


def test_it_looks_every_three_hours_and_hands_third_party_text(db, api):
    recorded, client = api
    owner = setup(db)
    turn_on(
        db,
        owner,
        client,
        picks("GITHUB_LIST_REPOSITORY_ISSUES", {"owner": "dono", "repo": "visao"}),
    )
    now = datetime.now(UTC)

    def look(at):
        return glance.background(db, owner, apps=client, secret_key=KEY, monthly_limit=1000, now=at)

    seen = look(now)
    assert executions(recorded) == 1
    [(app, text)] = seen.items()
    assert text.startswith("<<<texto de terceiros:") and text.endswith(
        "<<<fim do texto de terceiros>>>"
    )
    assert len(text) < glance.GLANCE_CHARS + 200
    body = json.loads(recorded.requests[-1].content)
    assert body["arguments"] == {"owner": "dono", "repo": "visao"}
    # Within three hours: the same text, no new call.
    assert look(now + timedelta(hours=2)) == seen
    assert executions(recorded) == 1
    look(now + timedelta(hours=3, minutes=1))
    assert executions(recorded) == 2


def test_near_the_month_ceiling_it_stops_looking(db, api, monkeypatch):
    recorded, client = api
    owner = setup(db)
    turn_on(db, owner, client, picks("GITHUB_LIST_REPOSITORY_ISSUES"))
    monkeypatch.setattr(account, "calls_this_month", lambda session, now=None: 80)
    seen = glance.background(db, owner, apps=client, secret_key=KEY, monthly_limit=100)
    assert seen is None and executions(recorded) == 0


def test_turned_off_or_an_app_failing_never_breaks_the_mind(db, api):
    recorded, client = api
    owner = setup(db)
    assert glance.background(db, owner, apps=client, secret_key=KEY, monthly_limit=1000) is None
    turn_on(db, owner, client, picks("GITHUB_LIST_REPOSITORY_ISSUES"))
    recorded.answers[("POST", EXECUTE)] = __import__("httpx").Response(500, json={"error": "x"})
    assert glance.background(db, owner, apps=client, secret_key=KEY, monthly_limit=1000) is None
    glance.turn_off(owner, "github")
    assert glance.chosen(owner) == {}


def test_the_mind_sees_what_the_apps_showed(db, api):
    from core.mind.think import MindConfig, think_once
    from tests.integration.test_mind import NOON, THOUGHT, llm, mind_budget

    _, client = api
    owner = setup(db)
    turn_on(db, owner, client, picks("GITHUB_LIST_REPOSITORY_ISSUES"))
    provider = llm({**THOUGHT, "say": ""})
    config = MindConfig(
        think_every=timedelta(minutes=20),
        initiatives_per_day=6,
        google_secret=KEY,
        apps_key="ck_test",
        apps_monthly_calls=1000,
    )
    think_once(db, owner=owner, provider=provider, budget=mind_budget(), config=config, now=NOON)
    context = json.loads(provider.prompts[-1][-1].content)
    [text] = context["apps"].values()
    assert "texto de terceiros" in text


def test_the_switch_on_the_apps_screen(client, db, api):
    from apps.api.llm import get_llm_provider
    from tests.integration.test_apps_api import owner as apps_owner

    _, headers = apps_owner(client, db)
    client.app.dependency_overrides[get_llm_provider] = lambda: picks(
        "GITHUB_LIST_REPOSITORY_ISSUES"
    )
    on = client.post("/apps/github/glance", json={"enabled": True}, headers=headers)
    assert on.status_code == 200 and on.json()["enabled"] is True and on.json()["tool_name"]
    [app] = client.get("/apps", headers=headers).json()["connected"]
    assert app["glance"] == on.json()["tool_name"]
    # Something that writes is refused with words for the screen.
    client.app.dependency_overrides[get_llm_provider] = lambda: picks("GITHUB_CREATE_AN_ISSUE")
    client.post("/apps/github/glance", json={"enabled": False}, headers=headers)
    refused = client.post("/apps/github/glance", json={"enabled": True}, headers=headers)
    assert refused.status_code == 422 and "leitura" in refused.json()["detail"]
    assert client.get("/apps", headers=headers).json()["connected"][0]["glance"] == ""
    # An app that is not connected cannot be watched.
    assert (
        client.post("/apps/notion/glance", json={"enabled": True}, headers=headers).status_code
        == 404
    )
