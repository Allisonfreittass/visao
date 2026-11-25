"""Changes in the owner's apps wait for a yes and run once (ADR-0028, step 3), with the rules of
core/google/actions.py: at most 5 waiting, proposed -> sending before running, expiry in 24 h,
"unknown" after a crash. Composio is answered from recorded responses."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.apps import account, actions
from infrastructure.database.models import AuditLog, Message, ToolAction
from integrations.composio.client import ComposioClient
from tests.fake_composio import RecordedComposio
from tests.integration.test_mind import setup
from tests.integration.test_mind_temperament import chat

pytest.importorskip("composio")

KEY = "chave-de-teste-com-mais-de-32-caracteres!!"
ISSUE = {"owner": "dono", "repo": "visao", "title": "Erro no login", "body": "Passos: ..."}


@pytest.fixture
def api():
    recorded = RecordedComposio()
    recorded.connected()
    account._CONNECTED.clear()
    return recorded


@pytest.fixture
def apps(api):
    return ComposioClient("chave-composio", http=api.http())


def tool(apps, slug="GITHUB_CREATE_AN_ISSUE"):
    return next(t for t in apps.tools("github") if t.slug == slug)


def approve(db, owner, action, apps, limit=8000):
    return actions.approve(db, owner, action.id, apps=apps, secret_key=KEY, monthly_limit=limit)


def executed(api, slug="GITHUB_CREATE_AN_ISSUE"):
    return api.sent("POST", f"/tools/execute/{slug}")


def test_a_write_waits_runs_once_when_approved_and_reports_in_the_conversation(db, api, apps):
    owner = setup(db)
    action = actions.propose(
        db,
        owner.id,
        tool=tool(apps),
        app_name="GitHub",
        arguments=ISSUE,
        conversation_id=chat(db, owner).id,
    )
    assert action.status == "proposed" and executed(api) == []
    assert (action.toolkit, action.tool_slug, action.tool_version) == (
        "github",
        "GITHUB_CREATE_AN_ISSUE",
        "20251111_00",
    )
    assert action.payload["arguments"] == ISSUE and actions.describe(action) == (
        "GitHub: Create an issue"
    )
    approve(db, owner, action, apps)
    assert action.status == "done" and len(executed(api)) == 1
    assert "https://github.com/dono/visao/issues/8" in action.result
    report = db.scalar(select(Message).where(Message.origin == "apps"))
    assert "Feito no GitHub: Create an issue" in report.content
    approve(db, owner, action, apps)
    assert len(executed(api)) == 1  # approving twice runs once
    [counted] = db.scalars(select(AuditLog).where(AuditLog.action == "composio_call"))
    assert counted.outcome == "success" and counted.details["kind"] == "write"


def test_two_approvals_at_the_same_time_run_once(db, api, apps):
    owner = setup(db)
    action = actions.propose(db, owner.id, tool=tool(apps), app_name="GitHub", arguments=ISSUE)
    db.commit()
    other = sessionmaker(bind=db.get_bind(), expire_on_commit=False)()
    seen = []
    run = apps.execute

    def run_while_the_other_approves(*args, **kwargs):
        seen.append(approve(other, owner, action, apps).status)
        return run(*args, **kwargs)

    apps.execute = run_while_the_other_approves
    approve(db, owner, action, apps)
    assert len(executed(api)) == 1 and action.status == "done"
    assert seen == ["sending"]
    other.close()


def test_destructive_is_never_proposed_and_is_checked_again_before_running(db, api, apps):
    owner = setup(db)
    with pytest.raises(actions.ActionError, match="apagar"):
        actions.propose(
            db,
            owner.id,
            tool=tool(apps, "GITHUB_DELETE_A_REPOSITORY"),
            app_name="GitHub",
            arguments={"owner": "dono", "repo": "visao"},
        )
    # Proposed while the hints said "star", and Composio now marks it destructive.
    action = actions.propose(
        db,
        owner.id,
        tool=tool(apps, "GITHUB_STAR_A_REPOSITORY"),
        app_name="GitHub",
        arguments={"owner": "dono", "repo": "visao"},
    )
    apps._tools.clear()
    listing = api.answers[("GET", "/api/v3.1/tools")]
    for item in listing["items"]:
        if item["slug"] == "GITHUB_STAR_A_REPOSITORY":
            item["tags"] = ["destructiveHint"]
    approve(db, owner, action, apps)
    assert action.status == "failed" and executed(api, "GITHUB_STAR_A_REPOSITORY") == []


def test_gmail_and_calendar_cannot_be_proposed_here(db, apps):
    from dataclasses import replace

    owner = setup(db)
    with pytest.raises(actions.ActionError, match="Google"):
        actions.propose(
            db,
            owner.id,
            tool=replace(tool(apps), toolkit="gmail"),
            app_name="Gmail",
            arguments={},
        )


def test_rejected_never_runs_and_too_many_waiting_is_refused(db, api, apps):
    owner = setup(db)
    first = actions.propose(db, owner.id, tool=tool(apps), app_name="GitHub", arguments=ISSUE)
    actions.reject(db, owner.id, first.id)
    approve(db, owner, first, apps)
    assert first.status == "rejected" and executed(api) == []
    for i in range(actions.MAX_PENDING):
        actions.propose(
            db, owner.id, tool=tool(apps), app_name="GitHub", arguments={**ISSUE, "title": str(i)}
        )
    with pytest.raises(actions.ActionError, match="demais"):
        actions.propose(db, owner.id, tool=tool(apps), app_name="GitHub", arguments=ISSUE)


def test_a_proposal_left_for_more_than_a_day_expires(db, api, apps):
    owner = setup(db)
    conversation = chat(db, owner)
    old = actions.propose(
        db,
        owner.id,
        tool=tool(apps),
        app_name="GitHub",
        arguments=ISSUE,
        conversation_id=conversation.id,
    )
    old.created_at = datetime.now(UTC) - actions.EXPIRES_AFTER - timedelta(minutes=1)
    db.flush()
    approve(db, owner, old, apps)
    assert old.status == "expired" and executed(api) == []
    told = db.scalar(select(Message).where(Message.origin == "apps"))
    assert "Passou um dia sem resposta" in told.content


def test_a_call_cut_by_a_crash_becomes_unknown_and_never_runs_again(db, api, apps):
    owner = setup(db)
    conversation = chat(db, owner)
    action = actions.propose(
        db,
        owner.id,
        tool=tool(apps),
        app_name="GitHub",
        arguments=ISSUE,
        conversation_id=conversation.id,
    )
    action.status = "sending"
    action.decided_at = datetime.now(UTC) - actions.STUCK_AFTER - timedelta(minutes=1)
    db.flush()
    assert actions.pending(db, owner.id) == [] and action.status == "unknown"
    told = db.scalar(select(Message).where(Message.origin == "apps"))
    assert "não sei se saiu" in told.content and "GitHub: Create an issue" in told.content
    approve(db, owner, action, apps)
    assert executed(api) == [] and action.status == "unknown"


def test_the_month_ceiling_stops_an_approved_write(db, api, apps):
    owner = setup(db)
    action = actions.propose(db, owner.id, tool=tool(apps), app_name="GitHub", arguments=ISSUE)
    approve(db, owner, action, apps, limit=0)
    assert action.status == "failed" and "limite do mês dos apps" in action.result
    assert executed(api) == []


def test_an_app_disconnected_meanwhile_does_not_run(db, api, apps):
    owner = setup(db)
    action = actions.propose(db, owner.id, tool=tool(apps), app_name="GitHub", arguments=ISSUE)
    api.answers[("GET", "/api/v3.1/connected_accounts")] = {"items": []}
    approve(db, owner, action, apps)
    assert action.status == "failed" and "não está mais conectado" in action.result
    assert executed(api) == []


def test_disconnecting_an_app_turns_down_only_its_own_proposals(db, apps):
    from dataclasses import replace

    owner = setup(db)
    github = actions.propose(db, owner.id, tool=tool(apps), app_name="GitHub", arguments=ISSUE)
    notion = actions.propose(
        db,
        owner.id,
        tool=replace(tool(apps), toolkit="notion", slug="NOTION_CREATE_PAGE"),
        app_name="Notion",
        arguments={"title": "x"},
    )
    assert actions.reject_app(db, owner.id, "github") == 1
    assert github.status == "rejected" and notion.status == "proposed"
    assert db.scalar(select(ToolAction).where(ToolAction.toolkit == "notion")) is notion
