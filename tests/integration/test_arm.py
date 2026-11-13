"""The arm: nothing runs without the owner's approval, and only on that owner's machines."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from core.arm import service
from core.initiatives import push
from infrastructure.database.models import ArmTask, Message
from tests.integration.test_mind import _owner_client
from tests.integration.test_push import RecordingSender, _subscribe


@pytest.fixture
def sender():
    recording = RecordingSender()
    push.configure(recording)
    yield recording
    push.configure(None)


def _pair(client, headers, name="MacBook"):
    response = client.post("/arm/devices", json={"name": name}, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["token"].startswith(service.TOKEN_PREFIX)
    return body, {"X-Visao-Arm-Token": body["token"]}


def _conversation(client, headers):
    return client.post("/conversations", headers=headers).json()["id"]


def test_the_owner_asks_the_arm_runs_and_the_answer_lands_in_the_conversation(client, db, sender):
    owner_user, owner = _owner_client(client, db)
    _subscribe(db, owner_user)
    device, arm = _pair(client, owner)
    chat = _conversation(client, owner)

    assert client.get("/arm/device/next", headers=arm).json() is None
    asked = client.post(
        "/arm/tasks",
        json={"project": "visao", "prompt": "rode os testes", "conversation_id": chat},
        headers=owner,
    ).json()
    assert asked["status"] == "approved" and asked["requested_by"] == "owner"

    job = client.get("/arm/device/next", headers=arm).json()
    assert job["id"] == asked["id"] and job["prompt"] == "rode os testes"
    assert client.get("/arm/device/next", headers=arm).json() is None  # taken once

    done = client.post(
        f"/arm/device/tasks/{job['id']}/result",
        json={"ok": True, "result": "613 passed", "cost_usd": "0.0123", "session_id": "s-1"},
        headers=arm,
    )
    assert done.status_code == 204
    [task] = client.get("/arm/tasks", headers=owner).json()
    assert task["status"] == "done" and task["claude_session_id"] == "s-1"
    assert Decimal(task["cost_usd"]) == Decimal("0.0123")
    trail = db.scalars(
        select(Message).where(Message.origin == "arm").order_by(Message.created_at)
    ).all()
    assert [m.role for m in trail] == ["user", "assistant", "assistant"]
    assert trail[0].content == "/mac visao rode os testes"
    assert "613 passed" in trail[-1].content and str(trail[-1].conversation_id) == chat
    assert sender.sent[-1][1]["url"] == f"/?c={chat}"


def test_an_agent_proposal_never_runs_until_the_owner_approves(client, db, sender):
    owner_user, owner = _owner_client(client, db)
    _subscribe(db, owner_user)
    _, arm = _pair(client, owner)
    task = service.propose(db, owner_user.id, "visao", "atualize as dependências")
    db.commit()
    assert sender.sent[-1][1]["title"] == "Posso fazer no seu Mac?"
    assert client.get("/arm/device/next", headers=arm).json() is None

    approved = client.post(f"/arm/tasks/{task.id}/approve", headers=owner)
    assert approved.json()["status"] == "approved"
    assert client.get("/arm/device/next", headers=arm).json()["id"] == str(task.id)


def test_rejecting_a_proposal_or_cancelling_before_it_starts(client, db):
    owner_user, owner = _owner_client(client, db)
    proposal = service.propose(db, owner_user.id, "visao", "x")
    db.commit()
    assert client.post(f"/arm/tasks/{proposal.id}/reject", headers=owner).json()["status"] == (
        "rejected"
    )
    asked = client.post("/arm/tasks", json={"project": "visao", "prompt": "y"}, headers=owner)
    cancelled = client.post(f"/arm/tasks/{asked.json()['id']}/reject", headers=owner)
    assert cancelled.json()["status"] == "cancelled"
    approve_again = client.post(f"/arm/tasks/{proposal.id}/approve", headers=owner)
    assert approve_again.status_code == 409


def test_a_machine_only_sees_its_owners_work_and_a_removed_one_is_cut_off(client, db):
    from apps.api.cli import create_user

    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    create_user(db, "outra@exemplo.com", "outra-senha-bem-longa")
    db.commit()
    token = client.post(
        "/auth/login", data={"username": "outra@exemplo.com", "password": "outra-senha-bem-longa"}
    ).json()["access_token"]
    stranger = {"Authorization": f"Bearer {token}"}
    device, other_arm = _pair(client, stranger, "Notebook da outra")

    client.post("/arm/tasks", json={"project": "visao", "prompt": "meu"}, headers=owner)
    assert client.get("/arm/device/next", headers=other_arm).json() is None
    job = client.get("/arm/device/next", headers=arm).json()
    assert job["prompt"] == "meu"
    # Another machine cannot answer for a task it does not hold.
    stolen = client.post(
        f"/arm/device/tasks/{job['id']}/result", json={"ok": True}, headers=other_arm
    )
    assert stolen.status_code == 404

    assert client.delete(f"/arm/devices/{device['id']}", headers=owner).status_code == 404
    assert client.delete(f"/arm/devices/{device['id']}", headers=stranger).status_code == 204
    assert client.get("/arm/device/next", headers=other_arm).status_code == 401


def test_heartbeat_shows_the_machine_online_with_its_projects(client, db):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    [before] = client.get("/arm/devices", headers=owner).json()
    assert before["online"] is False
    client.post(
        "/arm/device/heartbeat",
        json={"projects": ["visao", "rastros"], "version": "1"},
        headers=arm,
    )
    [after] = client.get("/arm/devices", headers=owner).json()
    assert after["online"] is True and after["projects"] == ["visao", "rastros"]


def test_bad_requests_and_unknown_tokens(client, db):
    _, owner = _owner_client(client, db)
    assert (
        client.post("/arm/tasks", json={"project": " ", "prompt": "x"}, headers=owner).status_code
        == 422
    )
    assert (
        client.get("/arm/device/next", headers={"X-Visao-Arm-Token": "visao-arm_nope"}).status_code
        == 401
    )
    assert client.get("/arm/device/next").status_code == 401
    assert client.get("/arm/tasks").status_code == 401


def test_a_task_the_mac_never_answered_is_marked_failed(client, db):
    from datetime import UTC, datetime, timedelta

    owner_user, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    client.post("/arm/tasks", json={"project": "visao", "prompt": "longa"}, headers=owner)
    job = client.get("/arm/device/next", headers=arm).json()
    task = db.get(ArmTask, __import__("uuid").UUID(job["id"]))
    task.started_at = datetime.now(UTC) - timedelta(hours=4)
    db.commit()
    [listed] = client.get("/arm/tasks", headers=owner).json()
    assert listed["status"] == "failed" and "Mac" in listed["error"]


def test_the_agent_is_told_what_its_arm_really_did(client, db, sender):
    """Real case (2026-11-12): the arm ran `git status`, the result landed in the chat as
    "Terminei no Mac", and on the next turn the agent apologised for having made it up. The reply
    prompt now carries the arm's record from the database, and the rule that it is real."""
    from apps.api.llm import get_llm_provider
    from tests.fakes import FakeLLMProvider

    llm = FakeLLMProvider(reply_text="Valeu!")
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    owner_user, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    client.post("/arm/device/heartbeat", json={"projects": ["visao"]}, headers=arm)
    chat = _conversation(client, owner)
    client.post(
        "/arm/tasks",
        json={"project": "visao", "prompt": "rode git status", "conversation_id": chat},
        headers=owner,
    )
    job = client.get("/arm/device/next", headers=arm).json()
    client.post(
        f"/arm/device/tasks/{job['id']}/result",
        json={"ok": True, "result": "On branch main\nnothing to commit, working tree clean"},
        headers=arm,
    )

    response = client.post(
        f"/conversations/{chat}/messages", headers=owner, json={"content": "você tá forte demais"}
    )
    assert response.status_code == 200, response.text
    system = llm.prompts[-1][0].content
    assert "registro do braço" in system
    assert 'projeto visao, pedida pelo dono: "rode git status". Situação: feita' in system
    assert "nothing to commit, working tree clean" in system
    assert "nunca diga que não rodou" in system
    history = [m.content for m in llm.prompts[-1][1:]]
    assert any(c.startswith("Terminei no Mac") for c in history)


def test_without_an_arm_the_prompt_says_nothing_about_it(db):
    from tests.integration.test_mind import setup

    owner = setup(db)
    assert service.work_record(db, owner.id) == ""


def test_an_approval_said_in_a_call_is_recorded_as_by_voice(client, db, sender):
    from sqlalchemy import select

    from infrastructure.database.models import AuditLog

    owner_user, owner = _owner_client(client, db)
    _pair(client, owner)
    task = service.propose(db, owner_user.id, "visao", "rode os testes")
    db.commit()

    approved = client.post(f"/arm/tasks/{task.id}/approve?via=voz", headers=owner)
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    log = db.scalars(select(AuditLog).where(AuditLog.action == "arm.approve")).all()[-1]
    assert log.details == {"via": "voz"}
    assert client.post(f"/arm/tasks/{task.id}/approve?via=grito", headers=owner).status_code == 422
