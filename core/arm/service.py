"""The arm's task queue (docs/BRACO.md).

Rules enforced here, not in a prompt:
- only the owner approves; the agent can only propose (`propose`), and a proposal never runs;
- an arm only ever receives approved tasks of its own owner, one at a time (`claim`);
- the result goes back to the conversation it came from, with a push when the app is closed;
- a result is never lost: sent twice it is taken once, and one that arrives after the task was
  given up (the Mac was silent) still replaces the failure;
- what a task changed is the list the arm measured with its photos, not what Claude says; undo
  is a task of its own, approved by the tap, that the arm runs without Claude;
- "até os testes passarem" is read from the owner's words in code, and the arm decides it by the
  exit code of the test command in braco.json.
"""

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.initiatives import push
from infrastructure.database.models import ArmDevice, ArmTask, Conversation, Message

TOKEN_PREFIX = "visao-arm_"  # noqa: S105 (a prefix to recognise device tokens, not a secret)
MAX_PROMPT = 8000
MAX_RESULT = 12_000
ONLINE_WINDOW = timedelta(seconds=90)
# A task an arm took and never answered (Mac closed mid-task) stops counting as running. Arms
# from version 2 beat while they work, so their silence says it much sooner.
STALE_RUNNING = timedelta(hours=3)
SILENT_ARM = timedelta(minutes=10)
# Between taking a task and the first beat that names it.
CLAIM_GRACE = timedelta(minutes=2)
STALE_ERROR = "O Mac não respondeu (desligou no meio?)."
LOST_ERROR = "O Mac não estava mais com essa tarefa (o braço reiniciou no meio?)."
OPEN = ("proposed", "approved", "running")
# Undo and "until the tests pass" need an arm of version 3; an older one would take the first as
# a prompt for Claude and run the second only once.
NEW_KINDS_VERSION = 3
TESTS_GOAL = re.compile(
    r"(?i)\bat[eé]\s+(?:que\s+)?(?:(?:todos\s+)?os?\s+)?testes?\s+pass\w*"
    r"|\bat[eé]\s+passar(?:em)?\s+(?:n[oa]s?\s+|em\s+)?(?:(?:todos\s+)?os?\s+)?testes?\b"
)
MAX_CHANGED_SHOWN = 30


class ArmError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Pairing:
    device: ArmDevice
    token: str  # shown once; only its hash is stored


def pair(session: Session, owner_id: uuid.UUID, name: str) -> Pairing:
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    device = ArmDevice(
        owner_user_id=owner_id,
        name=(name.strip() or "Mac")[:64],
        token_hash=token_hash(token),
        projects=[],
        version="",
    )
    session.add(device)
    session.flush()
    return Pairing(device, token)


def device_for_token(session: Session, token: str) -> ArmDevice | None:
    if not token.startswith(TOKEN_PREFIX):
        return None
    return session.scalar(select(ArmDevice).where(ArmDevice.token_hash == token_hash(token)))


def online(device: ArmDevice, now: datetime | None = None) -> bool:
    seen = _utc(device.last_seen_at)
    return seen is not None and (now or _now()) - seen < ONLINE_WINDOW


def wants_tests(prompt: str) -> bool:
    return TESTS_GOAL.search(prompt) is not None


def _version(device: ArmDevice) -> int:
    return int(device.version) if device.version.isdigit() else 0


def can_do_new_kinds(device: ArmDevice) -> bool:
    return _version(device) >= NEW_KINDS_VERSION


def beats_while_working(device: ArmDevice) -> bool:
    """Version 1 arms sent no beat during a task: their silence there means nothing."""
    return device.version not in ("", "1")


def heartbeat(
    session: Session,
    device: ArmDevice,
    projects: list[str],
    version: str,
    running: uuid.UUID | None = None,
) -> None:
    now = _now()
    device.projects = [p[:64] for p in projects[:50] if isinstance(p, str) and p.strip()]
    device.version = version[:32]
    device.last_seen_at = now
    if beats_while_working(device):
        # It says what it is working on: anything else it took (and is past the first beat)
        # was lost. A late result from it still lands (`finish`).
        for task in session.scalars(
            select(ArmTask).where(
                ArmTask.device_id == device.id,
                ArmTask.status == "running",
                ArmTask.started_at < now - CLAIM_GRACE,
            )
        ):
            if task.id != running:
                task.status, task.error, task.finished_at = "failed", LOST_ERROR, now
    session.flush()


def _validated(project: str, prompt: str) -> tuple[str, str]:
    project, prompt = project.strip(), prompt.strip()
    if not project or len(project) > 64:
        raise ArmError("Diga em qual projeto (um dos nomes configurados no Mac).")
    if not prompt:
        raise ArmError("Diga o que fazer.")
    if len(prompt) > MAX_PROMPT:
        raise ArmError(f"O pedido passa de {MAX_PROMPT} caracteres.")
    return project, prompt


def request(
    session: Session,
    owner_id: uuid.UUID,
    project: str,
    prompt: str,
    *,
    conversation_id: uuid.UUID | None = None,
    resume_session: str | None = None,
) -> ArmTask:
    """The owner asked: that request is the approval."""
    project, prompt = _validated(project, prompt)
    until = wants_tests(prompt)
    if until:
        _needs_new_arm(session, owner_id, "Para ir até os testes passarem")
    now = _now()
    task = ArmTask(
        owner_user_id=owner_id,
        conversation_id=conversation_id,
        project=project,
        prompt=prompt,
        status="approved",
        requested_by="owner",
        until_tests=until,
        resume_session=(resume_session or None),
        result="",
        error="",
        created_at=now,
        approved_at=now,
    )
    session.add(task)
    session.flush()
    return task


def propose(
    session: Session,
    owner_id: uuid.UUID,
    project: str,
    prompt: str,
    *,
    conversation_id: uuid.UUID | None = None,
    notify: bool = True,
) -> ArmTask:
    """The agent suggests work; it waits for the owner and tells them it is waiting."""
    project, prompt = _validated(project, prompt)
    task = ArmTask(
        owner_user_id=owner_id,
        conversation_id=conversation_id,
        project=project,
        prompt=prompt,
        status="proposed",
        requested_by="agent",
        until_tests=wants_tests(prompt),
        result="",
        error="",
    )
    session.add(task)
    session.flush()
    if not notify:
        return task
    push.send_to_owner(
        session,
        owner_id,
        title="Posso fazer no seu Mac?",
        body=f"{project}: {prompt}",
        url="/?mac=1",
        tag=f"visao-arm-{task.id}",
    )
    return task


def _needs_new_arm(session: Session, owner_id: uuid.UUID, what: str) -> None:
    devices = session.scalars(select(ArmDevice).where(ArmDevice.owner_user_id == owner_id)).all()
    if devices and not any(can_do_new_kinds(d) for d in devices):
        raise ArmError(f"{what}, atualize o braço no Mac: bash arm/instalar-mac.sh")


def can_undo(task: ArmTask) -> bool:
    return (
        task.kind == "work"
        and task.snapshot
        and task.undone_at is None
        and task.status in ("done", "failed")
        and bool(task.changed_files)
    )


def undo(session: Session, owner_id: uuid.UUID, task_id: uuid.UUID) -> ArmTask:
    """The tap on Desfazer is the approval. One undo per task, and only of a task whose photos
    the arm kept (version 3)."""
    original = _owned(session, owner_id, task_id)
    if not can_undo(original):
        raise ArmError("Essa tarefa não tem o que desfazer.")
    waiting = session.scalar(
        select(ArmTask.id).where(
            ArmTask.undo_of == original.id, ArmTask.status.in_(("approved", "running"))
        )
    )
    if waiting is not None:
        raise ArmError("Já pedi para desfazer essa tarefa.")
    _needs_new_arm(session, owner_id, "Para desfazer")
    now = _now()
    task = ArmTask(
        owner_user_id=owner_id,
        conversation_id=original.conversation_id,
        project=original.project,
        prompt=f"Desfazer: {_clip(original.prompt, 200)}",
        status="approved",
        requested_by="owner",
        kind="undo",
        undo_of=original.id,
        result="",
        error="",
        created_at=now,
        approved_at=now,
    )
    session.add(task)
    session.flush()
    return task


def _owned(session: Session, owner_id: uuid.UUID, task_id: uuid.UUID) -> ArmTask:
    task = session.get(ArmTask, task_id)
    if task is None or task.owner_user_id != owner_id:
        raise LookupError("task")
    return task


def approve(session: Session, owner_id: uuid.UUID, task_id: uuid.UUID) -> ArmTask:
    task = _owned(session, owner_id, task_id)
    if task.status != "proposed":
        raise ArmError("Só uma proposta pode ser aprovada.")
    task.status, task.approved_at = "approved", _now()
    session.flush()
    return task


def reject(session: Session, owner_id: uuid.UUID, task_id: uuid.UUID) -> ArmTask:
    task = _owned(session, owner_id, task_id)
    if task.status not in ("proposed", "approved"):
        raise ArmError("Essa tarefa já começou ou terminou.")
    task.status = "rejected" if task.status == "proposed" else "cancelled"
    task.finished_at = _now()
    session.flush()
    return task


def expire_stale(session: Session, owner_id: uuid.UUID, now: datetime | None = None) -> None:
    moment = now or _now()
    for task in session.scalars(
        select(ArmTask).where(ArmTask.owner_user_id == owner_id, ArmTask.status == "running")
    ):
        device = session.get(ArmDevice, task.device_id) if task.device_id else None
        started = _utc(task.started_at) or moment
        seen = _utc(device.last_seen_at) if device is not None else None
        silent = (
            device is not None
            and beats_while_working(device)
            and started < moment - CLAIM_GRACE
            and (seen is None or seen < moment - SILENT_ARM)
        )
        if silent or started < moment - STALE_RUNNING:
            task.status, task.error, task.finished_at = "failed", STALE_ERROR, moment
    session.flush()


def claim(session: Session, device: ArmDevice) -> ArmTask | None:
    """The oldest approved task of this device's owner, marked running for this device. The
    conditional update means two arms polling at once never get the same task."""
    query = select(ArmTask).where(
        ArmTask.owner_user_id == device.owner_user_id, ArmTask.status == "approved"
    )
    if not can_do_new_kinds(device):
        query = query.where(ArmTask.kind == "work", ArmTask.until_tests.is_(False))
    candidate = session.scalar(query.order_by(ArmTask.approved_at).limit(1))
    if candidate is None:
        return None
    taken = session.execute(
        update(ArmTask)
        .where(ArmTask.id == candidate.id, ArmTask.status == "approved")
        .values(status="running", device_id=device.id, started_at=_now())
    )
    session.flush()
    if taken.rowcount != 1:
        return None
    session.refresh(candidate)
    return candidate


_FILE_WORDS = {"A": "novo", "M": "mudou", "D": "apagado"}


def _files_line(task: ArmTask) -> str:
    """What the arm measured, in the task's own words: the agent and the owner see the same."""
    files = task.changed_files or []
    if task.kind == "undo":
        if task.status != "done" or not files:
            return ""
    elif not task.snapshot:
        return ""
    if not files:
        return "Nenhum arquivo mudou (conferido pelo braço)."
    shown = [
        f"- `{f.get('path', '')}` ({_FILE_WORDS.get(f.get('status', ''), '?')})" for f in files
    ]
    more = len(shown) - MAX_CHANGED_SHOWN
    lines = shown[:MAX_CHANGED_SHOWN] + ([f"- e mais {more}"] if more > 0 else [])
    head = (
        "Arquivos que voltaram:"
        if task.kind == "undo"
        else "Arquivos mudados (conferido pelo braço):"
    )
    return head + "\n" + "\n".join(lines)


def _tests_line(task: ArmTask) -> str:
    report = task.tests or {}
    if not report:
        return ""
    command, attempts = report.get("command", "?"), int(report.get("attempts") or 0)
    if report.get("passed"):
        where = "de primeira" if attempts <= 1 else f"na {attempts}ª tentativa"
        return f"Testes (`{command}`): passaram {where}."
    if report.get("error"):
        return f"Testes (`{command}`): {report['error']}"
    tail = str(report.get("tail") or "").strip()[-1500:]
    line = f"Testes (`{command}`): não passaram depois de {attempts} tentativa(s)."
    return f"{line}\n\n```\n{tail}\n```" if tail else line


def _summary(task: ArmTask) -> str:
    undo = task.kind == "undo"
    if task.status == "done":
        head = f"{'Desfiz' if undo else 'Terminei'} no Mac, em **{task.project}**."
        body = task.result.strip() or "Sem nada a relatar."
    else:
        head = f"Não {'consegui desfazer' if undo else 'deu certo'} no Mac, em **{task.project}**."
        body = task.error or "Erro sem detalhe."
        if task.result.strip() and not undo:
            body += "\n\n" + task.result.strip()
    parts = [head, body, _tests_line(task), _files_line(task)]
    return "\n\n".join(p for p in parts if p)[:MAX_RESULT]


def finish(
    session: Session,
    device: ArmDevice,
    task_id: uuid.UUID,
    *,
    ok: bool,
    result: str = "",
    error: str = "",
    cost_usd: Decimal | None = None,
    claude_session_id: str | None = None,
    changed: list[dict[str, str]] | None = None,
    snapshot: bool = False,
    tests: dict | None = None,
) -> ArmTask:
    task = session.get(ArmTask, task_id)
    if task is None or task.device_id != device.id:
        raise LookupError("task")
    given_up = task.status == "failed" and task.error in (STALE_ERROR, LOST_ERROR)
    if task.status in ("done", "failed") and not given_up:
        return task  # the same result sent again (the arm keeps it until it gets an answer)
    if task.status != "running" and not given_up:
        raise LookupError("task")
    now = _now()
    task.status = "done" if ok else "failed"
    task.result = result[:MAX_RESULT]
    task.error = error[:500]
    task.cost_usd = cost_usd
    task.claude_session_id = (claude_session_id or None) and claude_session_id[:128]
    task.finished_at = now
    task.snapshot = bool(snapshot) and task.kind == "work"
    task.changed_files = [
        {"path": str(c.get("path", ""))[:500], "status": str(c.get("status", ""))[:1]}
        for c in (changed or [])
        if isinstance(c, dict) and c.get("path")
    ] or ([] if snapshot or task.kind == "undo" else None)
    task.tests = tests if isinstance(tests, dict) else None
    if task.kind == "undo" and ok and task.undo_of is not None:
        original = session.get(ArmTask, task.undo_of)
        if original is not None and original.owner_user_id == task.owner_user_id:
            original.undone_at = now
    text = _summary(task)
    if task.conversation_id is not None:
        conversation = session.get(Conversation, task.conversation_id)
        if conversation is not None and conversation.user_id == task.owner_user_id:
            session.add(
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=text,
                    origin="arm",
                    created_at=now,
                )
            )
    session.flush()
    push.send_to_owner(
        session,
        task.owner_user_id,
        title=("Desfiz no Mac" if task.kind == "undo" else "Terminei no Mac")
        if ok
        else "Não deu certo no Mac",
        body=text,
        url=f"/?c={task.conversation_id}" if task.conversation_id else "/?mac=1",
        tag=f"visao-arm-{task.id}",
    )
    return task


def open_count(session: Session, owner_id: uuid.UUID) -> int:
    return len(
        session.scalars(
            select(ArmTask.id).where(ArmTask.owner_user_id == owner_id, ArmTask.status.in_(OPEN))
        ).all()
    )


# What the agent is told about its own work on the Mac, so it never disowns a real result (real
# case, 2026-11-12: it ran `git status` through the arm, then told the owner it had made it up).
RECORD_TASKS = 6
RECORD_WINDOW = timedelta(days=7)
RECORD_RESULT_CHARS = 600
_STATUS_WORDS = {
    "proposed": "proposta, esperando o sim do dono",
    "approved": "aprovada, esperando o Mac pegar",
    "running": "rodando agora no Mac",
    "done": "feita",
    "failed": "falhou",
    "rejected": "recusada pelo dono",
    "cancelled": "cancelada",
}


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def work_record(
    session: Session, owner_id: uuid.UUID, timezone: str = "UTC", now: datetime | None = None
) -> str:
    """The arm's devices and recent tasks as plain lines, or "" when there is no arm at all.

    Built from the database, never from what the model said: this is the record the truth
    rules point to when the history shows "Terminei no Mac"."""
    moment = now or _now()
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = ZoneInfo("UTC")

    def local(value: datetime | None) -> str:
        stamp = _utc(value)
        return stamp.astimezone(zone).strftime("%d/%m %H:%M") if stamp else "?"

    devices = session.scalars(select(ArmDevice).where(ArmDevice.owner_user_id == owner_id)).all()
    tasks = session.scalars(
        select(ArmTask)
        .where(ArmTask.owner_user_id == owner_id, ArmTask.created_at >= moment - RECORD_WINDOW)
        .order_by(ArmTask.created_at.desc())
        .limit(RECORD_TASKS)
    ).all()
    if not devices and not tasks:
        return ""
    lines = []
    for device in devices:
        state = (
            "ligado agora"
            if online(device, moment)
            else f"desligado, visto por último em {local(device.last_seen_at)}"
            if device.last_seen_at
            else "pareado, ainda não se conectou"
        )
        projects = ", ".join(p for p in (device.projects or []) if isinstance(p, str)) or "nenhum"
        lines.append(f'- Mac "{device.name}": {state}; projetos liberados: {projects}.')
    if not tasks:
        lines.append("- Nenhuma tarefa no Mac nos últimos 7 dias.")
    for task in reversed(tasks):
        who = "pedida pelo dono" if task.requested_by == "owner" else "proposta por você"
        status = _STATUS_WORDS.get(task.status, task.status)
        line = (
            f"- {local(task.created_at)}, projeto {task.project}, {who}: "
            f'"{_clip(task.prompt, 200)}". Situação: {status}'
        )
        if task.finished_at:
            line += f" às {local(task.finished_at)}"
        if task.status == "done" and task.result.strip():
            result = _clip(task.result, RECORD_RESULT_CHARS)
            line += f". Resultado devolvido pelo Claude Code: {result}"
        elif task.status == "failed" and task.error:
            line += f". Erro: {_clip(task.error, 200)}"
        if task.snapshot:
            line += f". Arquivos mudados, conferidos pelo braço: {len(task.changed_files or [])}"
        if task.tests:
            line += f". {_clip(_tests_line(task).split(chr(10))[0], 200)}"
        if task.undone_at:
            line += f". Desfeita pelo dono às {local(task.undone_at)}"
        lines.append(line + ".")
    return "\n".join(lines)
