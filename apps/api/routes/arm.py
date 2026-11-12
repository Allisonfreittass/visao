"""The arm (docs/BRACO.md): the owner's side (pair, ask, approve) and the machine's side
(heartbeat, take the next approved task, report). The two sides authenticate differently: the
owner with the login token, the machine with its own revocable device token."""

import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from apps.api.deps import CurrentUser, DbSession
from core.arm import service
from infrastructure.database.audit import record_audit
from infrastructure.database.models import ArmDevice, ArmTask, Conversation, Message

router = APIRouter(prefix="/arm", tags=["arm"])

MAX_DEVICES = 5
LONG_POLL_MAX = 25


class DeviceIn(BaseModel):
    name: str = Field(default="Mac", max_length=64)


class DeviceOut(BaseModel):
    id: uuid.UUID
    name: str
    projects: list[str]
    version: str
    online: bool
    last_seen_at: datetime | None


class PairingOut(DeviceOut):
    token: str


class TaskIn(BaseModel):
    project: str = Field(max_length=64)
    prompt: str = Field(max_length=service.MAX_PROMPT)
    conversation_id: uuid.UUID | None = None
    resume_session: str | None = Field(default=None, max_length=128)


class TaskOut(BaseModel):
    id: uuid.UUID
    project: str
    prompt: str
    status: str
    requested_by: str
    result: str
    error: str
    cost_usd: Decimal | None
    claude_session_id: str | None
    conversation_id: uuid.UUID | None
    created_at: datetime
    finished_at: datetime | None


class HeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    projects: list[str] = Field(default_factory=list, max_length=50)
    version: str = Field(default="", max_length=32)


class NextOut(BaseModel):
    id: uuid.UUID
    project: str
    prompt: str
    resume_session: str | None


class ResultIn(BaseModel):
    ok: bool
    result: str = Field(default="", max_length=200_000)
    error: str = Field(default="", max_length=5000)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    session_id: str | None = Field(default=None, max_length=128)


def _device_out(device: ArmDevice) -> dict:
    return {
        "id": device.id,
        "name": device.name,
        "projects": list(device.projects or []),
        "version": device.version,
        "online": service.online(device),
        "last_seen_at": device.last_seen_at,
    }


def _task_out(task: ArmTask) -> TaskOut:
    return TaskOut.model_validate(task, from_attributes=True)


# --- owner side ---------------------------------------------------------------------------


@router.get("/devices", response_model=list[DeviceOut])
def devices(user: CurrentUser, db: DbSession) -> list[dict]:
    rows = db.scalars(
        select(ArmDevice).where(ArmDevice.owner_user_id == user.id).order_by(ArmDevice.created_at)
    ).all()
    return [_device_out(d) for d in rows]


@router.post("/devices", response_model=PairingOut, status_code=status.HTTP_201_CREATED)
def pair(body: DeviceIn, user: CurrentUser, db: DbSession) -> dict:
    count = len(db.scalars(select(ArmDevice.id).where(ArmDevice.owner_user_id == user.id)).all())
    if count >= MAX_DEVICES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Limite de aparelhos atingido")
    pairing = service.pair(db, user.id, body.name)
    record_audit(db, "arm.pair", "success", actor_user_id=user.id)
    db.commit()
    return {**_device_out(pairing.device), "token": pairing.token}


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def unpair(device_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    device = db.get(ArmDevice, device_id)
    if device is None or device.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aparelho não encontrado")
    db.delete(device)
    record_audit(db, "arm.unpair", "success", actor_user_id=user.id)
    db.commit()


@router.get("/tasks", response_model=list[TaskOut])
def tasks(
    user: CurrentUser, db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[TaskOut]:
    service.expire_stale(db, user.id)
    db.commit()
    rows = db.scalars(
        select(ArmTask)
        .where(ArmTask.owner_user_id == user.id)
        .order_by(ArmTask.created_at.desc())
        .limit(limit)
    ).all()
    return [_task_out(t) for t in rows]


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def ask(body: TaskIn, user: CurrentUser, db: DbSession) -> TaskOut:
    if body.conversation_id is not None:
        conversation = db.get(Conversation, body.conversation_id)
        if conversation is None or conversation.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada")
    try:
        task = service.request(
            db,
            user.id,
            body.project,
            body.prompt,
            conversation_id=body.conversation_id,
            resume_session=body.resume_session,
        )
    except service.ArmError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    record_audit(
        db, "arm.request", "success", actor_user_id=user.id, details={"project": task.project}
    )
    if body.conversation_id is not None:
        # The request and its receipt are part of the conversation, like any other turn.
        now = service._now()
        db.add_all(
            [
                Message(
                    conversation_id=body.conversation_id,
                    role="user",
                    content=f"/mac {task.project} {task.prompt}",
                    origin="arm",
                    created_at=now,
                ),
                Message(
                    conversation_id=body.conversation_id,
                    role="assistant",
                    content=f"Mandei para o Mac, em **{task.project}**. Aviso quando terminar.",
                    origin="arm",
                    created_at=now + timedelta(milliseconds=1),
                ),
            ]
        )
    db.commit()
    return _task_out(task)


def _decide(action, task_id: uuid.UUID, user: CurrentUser, db: DbSession, name: str) -> TaskOut:
    try:
        task = action(db, user.id, task_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarefa não encontrada") from exc
    except service.ArmError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    record_audit(db, f"arm.{name}", "success", actor_user_id=user.id)
    db.commit()
    return _task_out(task)


@router.post("/tasks/{task_id}/approve", response_model=TaskOut)
def approve(task_id: uuid.UUID, user: CurrentUser, db: DbSession) -> TaskOut:
    return _decide(service.approve, task_id, user, db, "approve")


@router.post("/tasks/{task_id}/reject", response_model=TaskOut)
def reject(task_id: uuid.UUID, user: CurrentUser, db: DbSession) -> TaskOut:
    return _decide(service.reject, task_id, user, db, "reject")


# --- machine side -------------------------------------------------------------------------


def current_device(
    db: DbSession, x_visao_arm_token: Annotated[str | None, Header()] = None
) -> ArmDevice:
    device = service.device_for_token(db, x_visao_arm_token or "")
    if device is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Aparelho não reconhecido")
    return device


Device = Annotated[ArmDevice, Depends(current_device)]


@router.post("/device/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def device_heartbeat(body: HeartbeatIn, device: Device, db: DbSession) -> None:
    service.heartbeat(db, device, body.projects, body.version)
    db.commit()


@router.get("/device/next", response_model=NextOut | None)
def device_next(
    device: Device, db: DbSession, wait: Annotated[int, Query(ge=0, le=LONG_POLL_MAX)] = 0
) -> NextOut | None:
    """Long poll: answers as soon as an approved task exists, or null after `wait` seconds."""
    deadline = time.monotonic() + wait
    while True:
        device.last_seen_at = service._now()
        task = service.claim(db, device)
        db.commit()
        if task is not None:
            return NextOut(
                id=task.id,
                project=task.project,
                prompt=task.prompt,
                resume_session=task.resume_session,
            )
        if time.monotonic() >= deadline:
            return None
        time.sleep(1.0)


@router.post("/device/tasks/{task_id}/result", status_code=status.HTTP_204_NO_CONTENT)
def device_result(task_id: uuid.UUID, body: ResultIn, device: Device, db: DbSession) -> None:
    try:
        service.finish(
            db,
            device,
            task_id,
            ok=body.ok,
            result=body.result,
            error=body.error,
            cost_usd=body.cost_usd,
            claude_session_id=body.session_id,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarefa não está com este aparelho") from exc
    db.commit()
