"""The arm (docs/BRACO.md): the owner's side (pair, ask, approve) and the machine's side
(heartbeat, take the next approved task, report). The two sides authenticate differently: the
owner with the login token, the machine with its own revocable device token."""

import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from apps.api.deps import CurrentUser, DbSession
from apps.api.llm import get_code_provider
from apps.api.settings import Settings, get_settings
from core import brain
from core.arm import coder, local_llm, service
from infrastructure.database.audit import record_audit
from infrastructure.database.models import ArmDevice, ArmTask, Conversation, Message
from integrations.llm.base import LLMProvider

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
    kind: str
    undo_of: uuid.UUID | None
    until_tests: bool
    changed_files: list[dict[str, str]] | None
    tests: dict | None
    undone_at: datetime | None
    can_undo: bool
    executor: str | None
    steps: int


class HeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    projects: list[str] = Field(default_factory=list, max_length=50)
    version: str = Field(default="", max_length=32)
    # The task it is working on now (version 2 arms beat while they work).
    running: uuid.UUID | None = None


class NextOut(BaseModel):
    id: uuid.UUID
    project: str
    prompt: str
    resume_session: str | None
    kind: str = "work"
    undo_of: uuid.UUID | None = None
    until_tests: bool = False


class ChangedIn(BaseModel):
    path: str = Field(max_length=1000)
    status: Literal["A", "M", "D"]


class ResultIn(BaseModel):
    ok: bool
    result: str = Field(default="", max_length=200_000)
    error: str = Field(default="", max_length=5000)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    session_id: str | None = Field(default=None, max_length=128)
    # Version 3: measured by the arm's photos, and the test command's verdict.
    changed: list[ChangedIn] = Field(default_factory=list, max_length=2000)
    snapshot: bool = False
    tests: dict | None = None
    # Version 4: who coded it (ADR-0023).
    executor: Literal["claude_code", "visao"] | None = None


class PastStepIn(BaseModel):
    """One step of the arm's own executor, as the Mac reports it."""

    tool: str | None = Field(default=None, max_length=40)
    args: dict = Field(default_factory=dict)
    note: str = Field(default="", max_length=4000)
    result: str = Field(default="", max_length=20_000)
    ok: bool = True


class StepIn(BaseModel):
    tools: list[str] = Field(default_factory=list, max_length=20)
    steps: list[PastStepIn] = Field(default_factory=list, max_length=200)
    # What braco.json allows; the server applies the smaller of these and its own.
    max_steps: int = Field(ge=1, le=200)
    max_usd: Decimal = Field(ge=0, le=100)


class StepOut(BaseModel):
    action: dict | None = None
    invalid: str | None = None
    note: str = ""
    stop: str | None = None
    step: int | None = None
    cost_usd: Decimal | None = None
    model: str | None = None


class LlmNextOut(BaseModel):
    id: uuid.UUID
    model: str
    messages: list[dict[str, str]]
    max_output_tokens: int


class LlmResultIn(BaseModel):
    ok: bool
    text: str = Field(default="", max_length=local_llm.MAX_RESULT)
    error: str = Field(default="", max_length=5000)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class BrainOut(BaseModel):
    mode: brain.Mode
    # The Mac offering a local model right now (None: none online).
    local_model: str | None
    mac_online: bool


class BrainIn(BaseModel):
    mode: brain.Mode


def _device_out(device: ArmDevice) -> dict:
    return {
        "id": device.id,
        "name": device.name,
        "projects": list(device.projects or []),
        "version": device.version,
        "online": service.online(device),
        "last_seen_at": device.last_seen_at,
    }


def _task_out(task: ArmTask, undoing: frozenset[uuid.UUID] = frozenset()) -> TaskOut:
    """`undoing`: tasks with an undo already waiting, so the button is not offered twice."""
    fields = {name: getattr(task, name) for name in TaskOut.model_fields if name != "can_undo"}
    return TaskOut(**fields, can_undo=service.can_undo(task) and task.id not in undoing)


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
    undoing = frozenset(
        db.scalars(
            select(ArmTask.undo_of).where(
                ArmTask.owner_user_id == user.id,
                ArmTask.kind == "undo",
                ArmTask.status.in_(("approved", "running")),
            )
        ).all()
    )
    return [_task_out(t, undoing) for t in rows]


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


def _decide(
    action, task_id: uuid.UUID, user: CurrentUser, db: DbSession, name: str, via: str = "toque"
) -> TaskOut:
    try:
        task = action(db, user.id, task_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarefa não encontrada") from exc
    except service.ArmError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    record_audit(db, f"arm.{name}", "success", actor_user_id=user.id, details={"via": via})
    db.commit()
    return _task_out(task)


@router.post("/tasks/{task_id}/approve", response_model=TaskOut)
def approve(
    task_id: uuid.UUID, user: CurrentUser, db: DbSession, via: Literal["toque", "voz"] = "toque"
) -> TaskOut:
    """`via=voz`: said in a call after it read the task aloud (docs/VOICE.md); recorded."""
    return _decide(service.approve, task_id, user, db, "approve", via)


@router.post("/tasks/{task_id}/reject", response_model=TaskOut)
def reject(
    task_id: uuid.UUID, user: CurrentUser, db: DbSession, via: Literal["toque", "voz"] = "toque"
) -> TaskOut:
    return _decide(service.reject, task_id, user, db, "reject", via)


@router.post("/tasks/{task_id}/undo", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def undo(task_id: uuid.UUID, user: CurrentUser, db: DbSession) -> TaskOut:
    """The tap is the approval: the arm puts the files back without Claude."""
    try:
        task = service.undo(db, user.id, task_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarefa não encontrada") from exc
    except service.ArmError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    record_audit(
        db, "arm.undo", "success", actor_user_id=user.id, details={"project": task.project}
    )
    db.commit()
    return _task_out(task)


@router.get("/brain", response_model=BrainOut)
def brain_status(user: CurrentUser, db: DbSession) -> BrainOut:
    """Which model the Visão thinks with, and whether the Mac offers a local one now."""
    device = local_llm.available(db, user.id)
    macs = db.scalars(select(ArmDevice).where(ArmDevice.owner_user_id == user.id)).all()
    return BrainOut(
        mode=brain.get_mode(db),
        local_model=device.local_model if device is not None else None,
        mac_online=any(service.online(d) for d in macs),
    )


@router.put("/brain", response_model=BrainOut)
def brain_switch(body: BrainIn, user: CurrentUser, db: DbSession) -> BrainOut:
    brain.set_mode(db, body.mode, actor_user_id=user.id, via="ajustes")
    db.commit()
    return brain_status(user, db)


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
    service.heartbeat(db, device, body.projects, body.version, body.running)
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
                kind=task.kind,
                undo_of=task.undo_of,
                until_tests=task.until_tests,
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
            changed=[c.model_dump() for c in body.changed],
            snapshot=body.snapshot,
            tests=_tests(body.tests),
            executor=body.executor,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarefa não está com este aparelho") from exc
    db.commit()


@router.post("/device/tasks/{task_id}/step", response_model=StepOut)
def device_step(
    task_id: uuid.UUID,
    body: StepIn,
    device: Device,
    db: DbSession,
    provider: Annotated[LLMProvider | None, Depends(get_code_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """The arm's own executor (ADR-0023): the next action of a running task, asked of the model
    through the chain of providers allowed to read code. The keys stay here."""
    device.last_seen_at = service._now()
    try:
        return coder.step(
            db,
            device,
            task_id,
            provider=provider,
            tools=body.tools,
            steps=[coder.PastStep(**s.model_dump()) for s in body.steps],
            max_steps=coder.limit_steps(settings.arm_code_max_steps, body.max_steps),
            max_usd=coder.limit_usd(settings.arm_code_max_usd, body.max_usd),
            budget_chars=settings.arm_code_context_chars,
            max_output_tokens=min(
                coder.MAX_OUTPUT_TOKENS, settings.llm_budget_output_tokens_per_call
            ),
        )
    except coder.StepError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Essa tarefa não está rodando neste aparelho"
        ) from exc


def _tests(report: dict | None) -> dict | None:
    """Only the fields the summary uses, each bounded: it comes from the Mac."""
    if not isinstance(report, dict):
        return None
    out: dict = {
        "command": str(report.get("command") or "")[:200],
        "passed": report.get("passed") is True,
        "attempts": max(0, min(int(report.get("attempts") or 0), 20))
        if str(report.get("attempts") or "0").isdigit()
        else 0,
    }
    for key, limit in (("tail", 3000), ("error", 500)):
        if report.get(key):
            out[key] = str(report[key])[-limit:]
    return out


@router.get("/device/llm/next", response_model=LlmNextOut | None)
def device_llm_next(
    device: Device,
    db: DbSession,
    wait: Annotated[int, Query(ge=0, le=LONG_POLL_MAX)] = 0,
    model: Annotated[str | None, Query(max_length=64)] = None,
) -> LlmNextOut | None:
    """Long poll for the local model (docs/MODELO_LOCAL.md): `model` is what this Mac offers;
    answers with a question as soon as one waits, or null after `wait` seconds."""
    deadline = time.monotonic() + wait
    while True:
        local_llm.seen(db, device, model)
        call = local_llm.claim(db, device) if device.local_model else None
        db.commit()
        if call is not None:
            payload = call.payload or {}
            return LlmNextOut(
                id=call.id,
                model=device.local_model or "",
                messages=list(payload.get("messages") or []),
                max_output_tokens=int(payload.get("max_output_tokens") or 1024),
            )
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.3)


@router.post("/device/llm/{call_id}/result", status_code=status.HTTP_204_NO_CONTENT)
def device_llm_result(call_id: uuid.UUID, body: LlmResultIn, device: Device, db: DbSession) -> None:
    try:
        local_llm.finish(
            db,
            device,
            call_id,
            ok=body.ok,
            text=body.text,
            error=body.error,
            input_tokens=body.input_tokens,
            output_tokens=body.output_tokens,
        )
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Pergunta não está com este aparelho"
        ) from exc
    db.commit()
