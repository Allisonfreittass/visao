"""The Composio client and the owner's account there (ADR-0028, step 2): the only place that
imports the SDK, the owner sent as an HMAC, read and write told apart by the hints, destructive
never run, and the Visão's own ceiling a month counted in the audit log."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from apps.api.settings import Settings
from core.apps import account
from infrastructure.database.models import AuditLog
from integrations.composio.client import ComposioClient, ComposioError, kind_of
from tests.fake_composio import API, RecordedComposio
from tests.integration.test_mind import setup

pytest.importorskip("composio")

KEY = "chave-de-teste-com-mais-de-32-caracteres!!"


def apps(api: RecordedComposio) -> ComposioClient:
    return ComposioClient("chave-composio", http=api.http())


def test_the_key_and_the_ceiling_are_settings_and_blank_means_off():
    settings = Settings(composio_api_key="", _env_file=None)
    assert settings.composio_api_key is None and settings.composio_monthly_calls == 8000
    assert account.client(None) is None
    on = Settings(composio_api_key="ck_x", _env_file=None)
    assert on.composio_api_key.get_secret_value() == "ck_x"
    assert "ck_x" not in repr(on)


def test_only_the_sdk_client_imports_composio():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    importers = [
        str(p.relative_to(root))
        for folder in ("apps", "core", "integrations", "infrastructure")
        for p in (root / folder).rglob("*.py")
        if "import composio" in p.read_text(encoding="utf-8")
        or "from composio" in p.read_text(encoding="utf-8")
    ]
    assert importers == ["integrations/composio/client.py"]


def test_the_owner_goes_to_composio_as_an_hmac_of_the_server_key():
    owner = uuid.uuid4()
    ref = account.user_ref(owner, KEY)
    assert ref == account.user_ref(owner, KEY) and ref.startswith("visao-")
    assert str(owner) not in ref
    assert ref != account.user_ref(owner, "outra-chave-com-mais-de-32-caracteres!!")
    assert ref != account.user_ref(uuid.uuid4(), KEY)


def test_only_read_only_alone_is_a_read():
    assert kind_of(["readOnlyHint"]) == "read"
    assert kind_of(["readOnlyHint", "openWorldHint", "issues"]) == "read"
    assert kind_of([]) == "write"  # no hint: a write
    assert kind_of(["createHint"]) == "write"
    assert kind_of(["readOnlyHint", "updateHint"]) == "write"  # swapped hints: a write
    assert kind_of(["readOnlyHint", "idempotentHint"]) == "write"
    assert kind_of(["readOnlyHint", "someNewHint"]) == "write"
    assert kind_of(["readOnlyHint", "destructiveHint"]) == "destructive"


def test_tools_come_with_their_version_and_kind():
    api = RecordedComposio()
    tools = {t.slug: t for t in apps(api).tools("github")}
    assert tools["GITHUB_LIST_REPOSITORY_ISSUES"].kind == "read"
    assert tools["GITHUB_CREATE_AN_ISSUE"].kind == "write"
    assert tools["GITHUB_UPDATE_AN_ISSUE"].kind == "write"
    assert tools["GITHUB_STAR_A_REPOSITORY"].kind == "write"
    assert tools["GITHUB_DELETE_A_REPOSITORY"].kind == "destructive"
    assert tools["GITHUB_GET_AN_ISSUE"].version == "20251111_00"
    assert "owner" in tools["GITHUB_GET_AN_ISSUE"].parameters["properties"]


def test_a_tool_runs_at_its_pinned_version_for_the_hmac_user_and_no_telemetry():
    api = RecordedComposio()
    client = apps(api)
    tool = next(t for t in client.tools("github") if t.slug == "GITHUB_LIST_REPOSITORY_ISSUES")
    data = client.execute("visao-abc", tool, {"owner": "dono", "repo": "visao"})
    assert data["items"][0]["title"] == "Bug no login"
    [sent] = api.sent("POST", "/tools/execute/GITHUB_LIST_REPOSITORY_ISSUES")
    assert json.loads(sent.content)["version"] == "20251111_00"
    assert json.loads(sent.content)["user_id"] == "visao-abc"
    assert all(r.url.host == "backend.composio.dev" for r in api.requests)


def test_a_destructive_tool_is_never_executed_by_the_client():
    api = RecordedComposio()
    client = apps(api)
    tool = next(t for t in client.tools("github") if t.kind == "destructive")
    with pytest.raises(ComposioError) as refused:
        client.execute("visao-abc", tool, {"owner": "dono", "repo": "visao"})
    assert refused.value.kind == "refused"
    assert not any("/tools/execute/" in r.url.path for r in api.requests)


def test_a_failed_tool_and_a_429_become_one_error_each_without_retrying():
    api = RecordedComposio()
    client = apps(api)
    tool = next(t for t in client.tools("github") if t.slug == "GITHUB_GET_AN_ISSUE")
    api.answers[("POST", f"{API}/tools/execute/GITHUB_GET_AN_ISSUE")] = {
        "data": {},
        "successful": False,
        "error": "Issue not found",
    }
    with pytest.raises(ComposioError, match="Issue not found"):
        client.execute("u", tool, {})
    api.answers[("POST", f"{API}/tools/execute/GITHUB_GET_AN_ISSUE")] = httpx.Response(
        429, headers={"Retry-After": "30"}, json={"error": {"message": "slow down"}}
    )
    before = len(api.requests)
    with pytest.raises(ComposioError) as limited:
        client.execute("u", tool, {})
    assert limited.value.kind == "rate_limited"
    assert len(api.sent("POST", "/tools/execute/GITHUB_GET_AN_ISSUE")) == 2
    assert len(api.requests) - before <= 2  # the tool schema at most, and one try


def test_connecting_is_a_link_and_a_wait_and_disconnecting_revokes_then_deletes():
    api = RecordedComposio()
    client = apps(api)
    connection_id, url = client.start_connection("visao-abc", "github")
    assert connection_id == "ca_github1" and url.startswith("https://connect.composio.dev/")
    assert client.wait_for_connection(connection_id, timeout=5).status == "ACTIVE"
    client.disconnect("ca_github1")
    assert api.sent("POST", "/connected_accounts/ca_github1/revoke")
    assert api.sent("DELETE", "/connected_accounts/ca_github1")


def test_the_catalog_leaves_nothing_out_but_marks_what_needs_own_credentials():
    catalog = {t.slug: t for t in apps(RecordedComposio()).catalog()}
    assert {"github", "notion", "slack", "jira"} <= set(catalog)
    assert catalog["github"].managed and not catalog["jira"].managed


def test_gmail_and_calendar_never_count_as_connected_apps():
    api = RecordedComposio()
    api.answers[("GET", f"{API}/connected_accounts")] = {
        "items": [
            {"id": "ca_1", "status": "ACTIVE", "toolkit": {"slug": "github"}},
            {"id": "ca_2", "status": "ACTIVE", "toolkit": {"slug": "gmail"}},
            {"id": "ca_3", "status": "ACTIVE", "toolkit": {"slug": "googlecalendar"}},
        ]
    }
    ref = f"visao-{uuid.uuid4().hex}"
    assert [c.toolkit for c in account.connected(apps(api), ref)] == ["github"]


def test_the_month_ceiling_is_counted_in_the_audit_log(db):
    owner = setup(db)
    for _ in range(2):
        entry = account.spend_call(
            db, owner.id, toolkit="github", tool="GITHUB_GET_AN_ISSUE", kind="read", monthly_limit=2
        )
        entry.outcome = "success"
    with pytest.raises(account.BudgetError, match="limite do mês dos apps"):
        account.spend_call(db, owner.id, toolkit="github", tool="X", kind="read", monthly_limit=2)
    rows = list(db.scalars(select(AuditLog).where(AuditLog.action == "composio_call")))
    assert len(rows) == 2 and rows[0].details == {
        "toolkit": "github",
        "tool": "GITHUB_GET_AN_ISSUE",
        "kind": "read",
    }
    # Last month's calls do not count.
    for row in rows:
        row.created_at = datetime.now(UTC).replace(day=1) - timedelta(days=1)
    db.flush()
    assert account.calls_this_month(db) == 0
