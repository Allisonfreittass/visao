"""Changes in the owner's other apps: proposed by the agent, shown in full, run only after the
owner approves (docs/APPS.md, ADR-0028). The rules are the ones of core/google/actions.py.

The card shows the app, what the tool does in words and every argument in full, so an issue or a
message that tries to give orders can at most produce a proposal the owner reads first.

An approval runs once. It is claimed in the database (proposed -> sending) and committed before
anything goes to Composio, so a tap and a spoken "sim", or two phones, cannot run it twice. A
proposal left waiting more than EXPIRES_AFTER expires. One that stopped in "sending" (the server
died mid-call) becomes "unknown" and is never run again on its own: the owner is told to check.
Destructive tools are never proposed, and the hints are checked again right before running."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.apps import account
from core.initiatives import push
from infrastructure.database.models import Conversation, Message, ToolAction, User
from integrations.composio.client import ComposioClient, ComposioError, Tool, kind_of

MAX_PENDING = 5
EXPIRES_AFTER = timedelta(hours=24)
STUCK_AFTER = timedelta(minutes=5)
# The arguments, as JSON; a card the owner can read in full.
MAX_ARGUMENTS_CHARS = 12_000
EXPIRED_TEXT = "Passou um dia sem resposta, então não fiz. Se ainda quiser, me peça de novo."
UNKNOWN_TEXT = (
    "O servidor caiu enquanto eu fazia isso, então não sei se saiu. Confira no app antes de "
    "pedir de novo."
)
ORIGIN = "apps"


class ActionError(ValueError):
    pass


def _tidy(session: Session, owner_id: uuid.UUID, now: datetime) -> None:
    for action in session.scalars(
        select(ToolAction).where(
            ToolAction.owner_user_id == owner_id,
            ToolAction.status == "proposed",
            ToolAction.created_at <= now - EXPIRES_AFTER,
        )
    ):
        action.status, action.result, action.decided_at = "expired", EXPIRED_TEXT, now
    for action in session.scalars(
        select(ToolAction).where(
            ToolAction.owner_user_id == owner_id,
            ToolAction.status == "sending",
            ToolAction.decided_at <= now - STUCK_AFTER,
        )
    ):
        action.status, action.result = "unknown", UNKNOWN_TEXT
        _report(session, action, f"{describe(action)}. {UNKNOWN_TEXT}")
    session.flush()


def pending(session: Session, owner_id: uuid.UUID) -> list[ToolAction]:
    _tidy(session, owner_id, datetime.now(UTC))
    return list(
        session.scalars(
            select(ToolAction)
            .where(ToolAction.owner_user_id == owner_id, ToolAction.status == "proposed")
            .order_by(ToolAction.created_at)
        )
    )


def propose(
    session: Session,
    owner_id: uuid.UUID,
    *,
    tool: Tool,
    app_name: str,
    arguments: dict[str, Any],
    conversation_id: uuid.UUID | None = None,
) -> ToolAction:
    if tool.toolkit in account.EXCLUDED:
        raise ActionError("email e agenda são pela integração do Google")
    if tool.kind == "destructive":
        raise ActionError("apagar pelos apps está desligado")
    if not tool.version or tool.version == "latest":
        raise ActionError("a ferramenta veio sem versão")
    if not isinstance(arguments, dict):
        raise ActionError("argumentos inválidos")
    try:
        encoded = json.dumps(arguments, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ActionError("argumentos inválidos") from exc
    if len(encoded) > MAX_ARGUMENTS_CHARS:
        raise ActionError("o pedido é grande demais para mostrar inteiro")
    if len(pending(session, owner_id)) >= MAX_PENDING:
        raise ActionError("já há pedidos demais esperando você")
    action = ToolAction(
        owner_user_id=owner_id,
        conversation_id=conversation_id,
        kind="write",
        payload={
            "app": app_name[:80] or tool.toolkit,
            "tool_name": tool.name[:200] or tool.slug,
            "description": tool.description[:500],
            "tags": list(tool.tags)[:20],
            "arguments": json.loads(encoded),
        },
        status="proposed",
        result="",
        created_at=datetime.now(UTC),
        toolkit=tool.toolkit[:60],
        tool_slug=tool.slug[:120],
        tool_version=tool.version[:40],
    )
    session.add(action)
    session.flush()
    return action


def describe(action: ToolAction) -> str:
    p = action.payload
    return f"{p.get('app') or action.toolkit}: {p.get('tool_name') or action.tool_slug}"


def _owned(session: Session, owner_id: uuid.UUID, action_id: uuid.UUID) -> ToolAction:
    action = session.get(ToolAction, action_id)
    if action is None or action.owner_user_id != owner_id:
        raise LookupError("action")
    return action


def _report(session: Session, action: ToolAction, text: str) -> None:
    conversation = (
        session.get(Conversation, action.conversation_id) if action.conversation_id else None
    )
    if conversation is not None:
        session.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=text,
                origin=ORIGIN,
                created_at=datetime.now(UTC),
            )
        )


def reject(session: Session, owner_id: uuid.UUID, action_id: uuid.UUID) -> ToolAction:
    action = _owned(session, owner_id, action_id)
    if action.status == "proposed":
        action.status, action.decided_at = "rejected", datetime.now(UTC)
        session.flush()
    return action


def reject_app(session: Session, owner_id: uuid.UUID, toolkit: str) -> int:
    """Disconnecting an app turns down what was waiting from it, and nothing else."""
    dropped = 0
    for action in session.scalars(
        select(ToolAction).where(
            ToolAction.owner_user_id == owner_id,
            ToolAction.toolkit == toolkit,
            ToolAction.status == "proposed",
        )
    ):
        action.status, action.result = "rejected", "App desconectado."
        action.decided_at = datetime.now(UTC)
        dropped += 1
    session.flush()
    return dropped


def _claim(session: Session, owner_id: uuid.UUID, action_id: uuid.UUID, now: datetime) -> bool:
    claimed = session.execute(
        update(ToolAction)
        .where(
            ToolAction.id == action_id,
            ToolAction.owner_user_id == owner_id,
            ToolAction.status == "proposed",
            ToolAction.created_at > now - EXPIRES_AFTER,
        )
        .values(status="sending", decided_at=now)
        .execution_options(synchronize_session=False)
    )
    return claimed.rowcount == 1


def _finish(session: Session, owner: User, action: ToolAction) -> ToolAction:
    _report(session, action, action.result)
    session.flush()
    if action.status == "done" and action.conversation_id is None:
        push.send_to_owner(session, owner.id, title="Feito", body=action.result, url="/")
    return action


def _link(data: object) -> str:
    """A link to what was made, when the app returns one at the top."""
    if isinstance(data, dict):
        for key in ("html_url", "url", "permalink", "web_url", "link"):
            value = data.get(key)
            if isinstance(value, str) and value.startswith("https://"):
                return value[:300]
    return ""


def _still_safe(apps: ComposioClient, action: ToolAction) -> bool:
    """The hints are checked again right before running: a tool that became destructive since
    the proposal (or one no longer listed as safe) does not run."""
    if kind_of(action.payload.get("tags") or []) == "destructive":
        return False
    try:
        listed = next((t for t in apps.tools(action.toolkit) if t.slug == action.tool_slug), None)
    except ComposioError:
        return True  # the stored hints were checked; the call itself will fail if it is gone
    return listed is None or listed.kind != "destructive"


def approve(
    session: Session,
    owner: User,
    action_id: uuid.UUID,
    *,
    apps: ComposioClient | None,
    secret_key: str,
    monthly_limit: int,
) -> ToolAction:
    action = _owned(session, owner.id, action_id)
    now = datetime.now(UTC)
    if not _claim(session, owner.id, action_id, now):
        session.refresh(action)
        if action.status == "proposed":
            action.status, action.result, action.decided_at = "expired", EXPIRED_TEXT, now
            return _finish(session, owner, action)
        return action  # already decided, or being run right now by the other approval
    # The claim reaches every other request before anything goes out.
    session.commit()
    session.refresh(action)
    app = action.payload.get("app") or action.toolkit
    if apps is None:
        action.status, action.result = "failed", "Os apps estão desligados neste servidor."
        return _finish(session, owner, action)
    if not _still_safe(apps, action):
        action.status, action.result = "failed", "Essa ferramenta apaga coisas; não fiz."
        return _finish(session, owner, action)
    ref = account.user_ref(owner.id, secret_key)
    if action.toolkit not in {c.toolkit for c in account.connected(apps, ref, fresh=True)}:
        action.status, action.result = "failed", f"O {app} não está mais conectado; não fiz."
        return _finish(session, owner, action)
    tool = Tool(
        slug=action.tool_slug,
        name=str(action.payload.get("tool_name") or ""),
        description="",
        toolkit=action.toolkit,
        version=action.tool_version,
        tags=tuple(action.payload.get("tags") or ()),
    )
    try:
        entry = account.spend_call(
            session,
            owner.id,
            toolkit=action.toolkit,
            tool=action.tool_slug,
            kind="write",
            monthly_limit=monthly_limit,
        )
    except account.BudgetError:
        action.status, action.result = "failed", f"Não fiz: {account.MONTH_OVER}."
        return _finish(session, owner, action)
    # The count reaches the database before the call, like the claim.
    session.commit()
    try:
        data = apps.execute(ref, tool, action.payload.get("arguments") or {})
    except ComposioError as exc:
        entry.outcome = "failure"
        action.status, action.result = "failed", f"Não deu: {exc}."[:500]
        return _finish(session, owner, action)
    entry.outcome = "success"
    link = _link(data)
    action.status = "done"
    action.result = (
        f"Feito no {app}: {action.payload.get('tool_name') or action.tool_slug}."
        + (f" {link}" if link else "")
    )[:500]
    return _finish(session, owner, action)
