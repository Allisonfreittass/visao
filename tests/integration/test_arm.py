"""The arm: nothing runs without the owner's approval, and only on that owner's machines."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from core.arm import service
from core.initiatives import push
from infrastructure.database.models import ArmDevice, ArmTask, Message
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


# F4: a result is never lost ------------------------------------------------------------------


def _running(client, db, owner, arm, version="2"):
    import uuid

    client.post(
        "/arm/device/heartbeat", json={"projects": ["visao"], "version": version}, headers=arm
    )
    client.post("/arm/tasks", json={"project": "visao", "prompt": "longa"}, headers=owner)
    job = client.get("/arm/device/next", headers=arm).json()
    return db.get(ArmTask, uuid.UUID(job["id"]))


def _arm_replies(db):
    return db.scalars(
        select(Message).where(Message.origin == "arm", Message.role == "assistant")
    ).all()


def test_the_same_result_sent_twice_is_taken_once(client, db, sender):
    owner_user, owner = _owner_client(client, db)
    _subscribe(db, owner_user)
    _, arm = _pair(client, owner)
    task = _running(client, db, owner, arm)
    for _ in range(2):  # the arm sends again when it did not hear back
        sent = client.post(
            f"/arm/device/tasks/{task.id}/result", json={"ok": True, "result": "ok"}, headers=arm
        )
        assert sent.status_code == 204
    assert len(sender.sent) == 1  # one "Terminei no Mac", not two


def test_a_result_that_arrives_after_the_task_was_given_up_still_lands(client, db, sender):
    from datetime import UTC, datetime, timedelta

    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    task = _running(client, db, owner, arm, version="1")
    task.started_at = datetime.now(UTC) - timedelta(hours=4)
    db.commit()
    [listed] = client.get("/arm/tasks", headers=owner).json()
    assert listed["status"] == "failed"
    late = client.post(
        f"/arm/device/tasks/{task.id}/result",
        json={"ok": True, "result": "613 passed"},
        headers=arm,
    )
    assert late.status_code == 204
    [listed] = client.get("/arm/tasks", headers=owner).json()
    assert listed["status"] == "done" and listed["result"] == "613 passed"


def test_a_beat_that_names_another_task_gives_up_the_lost_one(client, db):
    from datetime import UTC, datetime, timedelta

    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    task = _running(client, db, owner, arm)

    def beat(running):
        client.post(
            "/arm/device/heartbeat",
            json={"projects": ["visao"], "version": "2", "running": running},
            headers=arm,
        )
        db.refresh(task)

    beat(None)
    assert task.status == "running"  # just taken: the first beat that names it may not have come
    task.started_at = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()
    beat(str(task.id))
    assert task.status == "running"
    beat(None)
    assert task.status == "failed" and task.error == service.LOST_ERROR


def test_a_silent_mac_gives_up_its_task_in_minutes_not_hours(client, db):
    from datetime import UTC, datetime, timedelta

    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    old_arm = _pair(client, owner, "Mac antigo")[1]
    task = _running(client, db, owner, arm)
    old_task = _running(client, db, owner, old_arm, version="1")
    quiet = datetime.now(UTC) - timedelta(minutes=15)
    for each in (task, old_task):
        each.started_at = quiet
        db.get(ArmDevice, each.device_id).last_seen_at = quiet
    db.commit()
    listed = {t["id"]: t["status"] for t in client.get("/arm/tasks", headers=owner).json()}
    # Version 2 beats while working, so 15 min of silence means it is gone; version 1 does not.
    assert listed[str(task.id)] == "failed" and listed[str(old_task.id)] == "running"


# Version 3: measured files, undo, until the tests pass ---------------------------------------

CHANGED = [
    {"path": "core/a.py", "status": "M"},
    {"path": "tests/test_a.py", "status": "A"},
    {"path": "velho.txt", "status": "D"},
]


def _beat(client, arm, version="3"):
    client.post(
        "/arm/device/heartbeat", json={"projects": ["visao"], "version": version}, headers=arm
    )


def _done_with_files(client, db, owner, arm, chat=None):
    _beat(client, arm)
    body = {"project": "visao", "prompt": "conserta o login"}
    if chat:
        body["conversation_id"] = chat
    client.post("/arm/tasks", json=body, headers=owner)
    job = client.get("/arm/device/next", headers=arm).json()
    client.post(
        f"/arm/device/tasks/{job['id']}/result",
        json={"ok": True, "result": "consertei", "changed": CHANGED, "snapshot": True},
        headers=arm,
    )
    return job


def test_the_files_a_task_changed_are_what_the_arm_measured(client, db, sender):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    chat = _conversation(client, owner)
    _done_with_files(client, db, owner, arm, chat)
    [task] = client.get("/arm/tasks", headers=owner).json()
    assert task["changed_files"] == CHANGED and task["can_undo"] is True
    reply = _arm_replies(db)[-1].content
    assert "Arquivos mudados (conferido pelo braço):" in reply
    assert "`core/a.py` (mudou)" in reply and "`tests/test_a.py` (novo)" in reply
    record = service.work_record(db, task_owner(db))
    assert "Arquivos mudados, conferidos pelo braço: 3" in record


def task_owner(db):
    return db.scalars(select(ArmTask.owner_user_id)).first()


def test_undo_is_a_task_of_its_own_that_the_arm_runs_without_claude(client, db, sender):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    chat = _conversation(client, owner)
    job = _done_with_files(client, db, owner, arm, chat)

    undo = client.post(f"/arm/tasks/{job['id']}/undo", headers=owner)
    assert undo.status_code == 201 and undo.json()["kind"] == "undo"
    again = client.post(f"/arm/tasks/{job['id']}/undo", headers=owner)
    assert again.status_code == 409  # one undo at a time
    listed = {t["id"]: t for t in client.get("/arm/tasks", headers=owner).json()}
    assert listed[job["id"]]["can_undo"] is False  # not offered while one waits

    taken = client.get("/arm/device/next", headers=arm).json()
    assert taken["kind"] == "undo" and taken["undo_of"] == job["id"]
    client.post(
        f"/arm/device/tasks/{taken['id']}/result",
        json={"ok": True, "result": "Voltei 3 arquivo(s).", "changed": CHANGED},
        headers=arm,
    )
    tasks = {t["id"]: t for t in client.get("/arm/tasks", headers=owner).json()}
    assert tasks[job["id"]]["undone_at"] is not None and tasks[job["id"]]["can_undo"] is False
    assert tasks[taken["id"]]["can_undo"] is False  # an undo is not undone
    reply = _arm_replies(db)[-1].content
    assert reply.startswith("Desfiz no Mac") and "Arquivos que voltaram:" in reply
    assert client.post(f"/arm/tasks/{job['id']}/undo", headers=owner).status_code == 409


def test_nothing_to_undo_without_the_arms_photos(client, db):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    task = _running(client, db, owner, arm, version="3")
    client.post(f"/arm/device/tasks/{task.id}/result", json={"ok": True}, headers=arm)
    assert client.post(f"/arm/tasks/{task.id}/undo", headers=owner).status_code == 409


def test_an_older_arm_never_gets_an_undo_or_a_tests_goal(client, db):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    job = _done_with_files(client, db, owner, arm)
    assert client.post(f"/arm/tasks/{job['id']}/undo", headers=owner).status_code == 201
    _beat(client, arm, version="2")  # the Mac went back to an old arm
    assert client.get("/arm/device/next", headers=arm).json() is None  # it would ask Claude
    refused = client.post(
        "/arm/tasks",
        json={"project": "visao", "prompt": "conserta até os testes passarem"},
        headers=owner,
    )
    assert refused.status_code == 422 and "instalar-mac.sh" in refused.json()["detail"]


def test_until_the_tests_pass_is_read_from_the_owners_words(client, db, sender):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    chat = _conversation(client, owner)
    _beat(client, arm)
    asked = client.post(
        "/arm/tasks",
        json={
            "project": "visao",
            "prompt": "conserta o login até os testes passarem",
            "conversation_id": chat,
        },
        headers=owner,
    ).json()
    assert asked["until_tests"] is True
    job = client.get("/arm/device/next", headers=arm).json()
    assert job["until_tests"] is True
    client.post(
        f"/arm/device/tasks/{job['id']}/result",
        json={
            "ok": True,
            "result": "consertei",
            "tests": {"command": "make check", "passed": True, "attempts": 2, "tail": "ok"},
        },
        headers=arm,
    )
    assert "Testes (`make check`): passaram na 2ª tentativa." in _arm_replies(db)[-1].content

    plain = client.post(
        "/arm/tasks", json={"project": "visao", "prompt": "roda os testes"}, headers=owner
    ).json()
    assert plain["until_tests"] is False


def test_tests_that_never_passed_show_the_end_of_the_output(client, db, sender):
    _, owner = _owner_client(client, db)
    _, arm = _pair(client, owner)
    chat = _conversation(client, owner)
    _beat(client, arm)
    client.post(
        "/arm/tasks",
        json={"project": "visao", "prompt": "até passar nos testes", "conversation_id": chat},
        headers=owner,
    )
    job = client.get("/arm/device/next", headers=arm).json()
    client.post(
        f"/arm/device/tasks/{job['id']}/result",
        json={
            "ok": False,
            "error": "Os testes (`make check`) não passaram depois de 3 tentativa(s).",
            "result": "tentei de tudo",
            "tests": {"command": "make check", "passed": False, "attempts": 3, "tail": "2 failed"},
        },
        headers=arm,
    )
    reply = _arm_replies(db)[-1].content
    assert reply.startswith("Não deu certo no Mac") and "tentei de tudo" in reply
    assert "não passaram depois de 3 tentativa(s)" in reply and "2 failed" in reply
