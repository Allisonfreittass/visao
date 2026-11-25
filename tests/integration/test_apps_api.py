"""Ajustes › Apps and the approval card through the API (ADR-0028, step 5): off without the key,
the catalog without Gmail and Calendar, connect with a wait, disconnect as revoke + delete, and
approving twice runs once. Composio is answered from recorded responses."""

import json

import pytest
from sqlalchemy import select

from apps.api.settings import Settings, get_settings
from core.apps import account, actions
from infrastructure.database.models import AuditLog, ToolAction
from integrations.composio.client import ComposioClient
from tests.fake_composio import API, RecordedComposio
from tests.integration.test_mind import _owner_client

pytest.importorskip("composio")

KEY = "chave-de-teste-com-mais-de-32-caracteres!!"


@pytest.fixture
def api(monkeypatch):
    recorded = RecordedComposio()
    account._CONNECTED.clear()
    client = ComposioClient("chave-composio", http=recorded.http())
    monkeypatch.setattr(account, "client", lambda key: client if key == "ck_test" else None)
    return recorded


def owner(client, db, key="ck_test"):
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        secret_key=KEY, composio_api_key=key, _env_file=None
    )
    return _owner_client(client, db)


def test_without_the_key_the_section_is_off(client, db, api):
    _, headers = owner(client, db, key=None)
    assert client.get("/apps", headers=headers).json()["enabled"] is False
    assert client.get("/apps/catalog", headers=headers).status_code == 404
    assert client.post("/apps/github/connect", headers=headers).status_code == 404
    assert api.requests == []


def test_the_catalog_has_every_app_but_gmail_and_calendar(client, db, api):
    _, headers = owner(client, db)
    slugs = {a["slug"] for a in client.get("/apps/catalog", headers=headers).json()}
    assert {"github", "notion", "slack", "jira", "perplexityai"} <= slugs
    assert not slugs & {"gmail", "googlecalendar"}
    items = {a["slug"]: a for a in client.get("/apps/catalog", headers=headers).json()}
    assert items["perplexityai"]["connectable"] and items["perplexityai"]["asks_key"]
    assert items["github"]["connectable"] and not items["github"]["asks_key"]
    assert not items["jira"]["connectable"]


def test_connecting_waits_for_the_owner_and_says_where_the_connection_lives(client, db, api):
    person, headers = owner(client, db)
    state = client.get("/apps", headers=headers).json()
    assert state["enabled"] is True and state["connected"] == []
    assert "fica guardada no Composio, não no Visão" in state["notice"]
    assert "até um ano" in state["notice"]
    started = client.post("/apps/github/connect", headers=headers).json()
    assert started["url"].startswith("https://connect.composio.dev/")
    [link] = api.sent("POST", "/connected_accounts/link")
    assert account.user_ref(person.id, KEY).encode() in link.content
    assert person.email.encode() not in link.content

    api.connected()
    done = client.post(
        f"/apps/connections/{started['connection_id']}/wait?timeout=5", headers=headers
    ).json()
    assert [a["toolkit"] for a in done["connected"]] == ["github"]
    assert done["connected"][0]["name"] == "GitHub"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "apps.connect"))


def test_gmail_and_apps_needing_own_credentials_cannot_be_connected_here(client, db, api):
    _, headers = owner(client, db)
    assert client.post("/apps/gmail/connect", headers=headers).status_code == 404
    assert client.post("/apps/jira/connect", headers=headers).status_code == 400
    assert api.sent("POST", "/connected_accounts/link") == []


def test_disconnecting_revokes_deletes_and_turns_down_what_waited(client, db, api):
    person, headers = owner(client, db)
    api.connected()
    apps = account.client("ck_test")
    tool = next(t for t in apps.tools("github") if t.slug == "GITHUB_CREATE_AN_ISSUE")
    waiting = actions.propose(
        db, person.id, tool=tool, app_name="GitHub", arguments={"owner": "a", "repo": "b"}
    )
    db.commit()
    assert client.delete("/apps/github", headers=headers).status_code == 204
    assert api.sent("POST", "/connected_accounts/ca_github1/revoke")
    assert api.sent("DELETE", "/connected_accounts/ca_github1")
    db.refresh(waiting)
    assert waiting.status == "rejected"


def test_the_card_lists_every_argument_and_approving_twice_runs_once(client, db, api):
    person, headers = owner(client, db)
    api.connected()
    apps = account.client("ck_test")
    tool = next(t for t in apps.tools("github") if t.slug == "GITHUB_CREATE_AN_ISSUE")
    arguments = {"owner": "dono", "repo": "visao", "title": "Erro", "body": "Texto inteiro"}
    action = actions.propose(db, person.id, tool=tool, app_name="GitHub", arguments=arguments)
    db.commit()
    [card] = client.get("/apps/actions", headers=headers).json()
    assert card["summary"] == "GitHub: Create an issue" and card["arguments"] == arguments
    assert card["version"] == "20251111_00" and card["tool_name"] == "Create an issue"
    first = client.post(f"/apps/actions/{action.id}/approve", headers=headers).json()
    again = client.post(f"/apps/actions/{action.id}/approve?via=voz", headers=headers).json()
    assert first["status"] == again["status"] == "done"
    assert len(api.sent("POST", "/tools/execute/GITHUB_CREATE_AN_ISSUE")) == 1
    assert client.get("/apps", headers=headers).json()["calls_this_month"] == 1


def test_rejecting_runs_nothing(client, db, api):
    person, headers = owner(client, db)
    api.connected()
    apps = account.client("ck_test")
    tool = next(t for t in apps.tools("github") if t.slug == "GITHUB_CREATE_AN_ISSUE")
    action = actions.propose(db, person.id, tool=tool, app_name="GitHub", arguments={})
    db.commit()
    out = client.post(f"/apps/actions/{action.id}/reject", headers=headers).json()
    assert out["status"] == "rejected"
    assert not any("/tools/execute/" in r.url.path for r in api.requests)
    db.refresh(action)
    assert action.status == "rejected" and db.scalar(select(ToolAction)) is action


def test_someone_elses_action_is_not_found(client, db, api):
    _, headers = owner(client, db)
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/apps/actions/{missing}/approve", headers=headers).status_code == 404


def test_an_app_asking_for_its_own_key_is_connected_through_composios_page(client, db, api):
    _, headers = owner(client, db)
    api.answers[("GET", f"{API}/auth_configs")] = {"items": []}
    api.answers[("POST", f"{API}/auth_configs")] = {
        "auth_config": {"id": "ac_novo", "auth_scheme": "API_KEY", "is_composio_managed": False},
        "toolkit": {"slug": "perplexityai"},
    }
    started = client.post("/apps/perplexityai/connect", headers=headers).json()
    assert started["url"].startswith("https://connect.composio.dev/")
    [created] = api.sent("POST", "/auth_configs")
    assert json.loads(created.content)["auth_config"]["authScheme"] == "API_KEY"
