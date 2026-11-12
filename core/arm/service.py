"""The arm's task queue (docs/BRACO.md).

Rules enforced here, not in a prompt:
- only the owner approves; the agent can only propose (`propose`), and a proposal never runs;
- an arm only ever receives approved tasks of its own owner, one at a time (`claim`);
- the result goes back to the conversation it came from, with a push when the app is closed.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.initiatives import push
from infrastructure.database.models import ArmDevice, ArmTask, Conversation, Message

TOKEN_PREFIX = "visao-arm_"  # noqa: S105 (a prefix to recognise device tokens, not a secret)
MAX_PROMPT = 8000
MAX_RESULT = 12_000
ONLINE_WINDOW = timedelta(seconds=90)
# A task an arm took and never answered (Mac closed mid-task) stops counting as running.
STALE_RUNNING = timedelta(hours=3)
OPEN = ("proposed", "approved", "running")


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


def heartbeat(session: Session, device: ArmDevice, projects: list[str], version: str) -> None:
    device.projects = [p[:64] for p in projects[:50] if isinstance(p, str) and p.strip()]
    device.version = version[:32]
    device.last_seen_at = _now()
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
    now = _now()
    task = ArmTask(
        owner_user_id=owner_id,
        conversation_id=conversation_id,
        project=project,
        prompt=prompt,
        status="approved",
        requested_by="owner",
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
    cutoff = moment - STALE_RUNNING
    session.execute(
        update(ArmTask)
        .where(
            ArmTask.owner_user_id == owner_id,
            ArmTask.status == "running",
            ArmTask.started_at < cutoff,
        )
        .values(
            status="failed", error="O Mac não respondeu (desligou no meio?).", finished_at=moment
        )
    )


def claim(session: Session, device: ArmDevice) -> ArmTask | None:
    """The oldest approved task of this device's owner, marked running for this device. The
    conditional update means two arms polling at once never get the same task."""
    candidate = session.scalar(
        select(ArmTask)
        .where(ArmTask.owner_user_id == device.owner_user_id, ArmTask.status == "approved")
        .order_by(ArmTask.approved_at)
        .limit(1)
    )
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


def _summary(task: ArmTask) -> str:
    if task.status == "done":
        head = f"Terminei no Mac, em **{task.project}**."
        body = task.result.strip() or "Sem nada a relatar."
    else:
        head = f"Não deu certo no Mac, em **{task.project}**."
        body = task.error or "Erro sem detalhe."
    return f"{head}\n\n{body}"[:MAX_RESULT]


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
) -> ArmTask:
    task = session.get(ArmTask, task_id)
    if task is None or task.device_id != device.id or task.status != "running":
        raise LookupError("task")
    now = _now()
    task.status = "done" if ok else "failed"
    task.result = result[:MAX_RESULT]
    task.error = error[:500]
    task.cost_usd = cost_usd
    task.claude_session_id = (claude_session_id or None) and claude_session_id[:128]
    task.finished_at = now
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
        title="Terminei no Mac" if ok else "Não deu certo no Mac",
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
