"""The owner's other apps through Composio (docs/APPS.md, ADR-0028): the catalog, connect (a link
the owner opens, then a wait), disconnect (revoke and delete there), and approve or reject the
changes it prepared. Without VISION_COMPOSIO_API_KEY everything here answers "off"."""

import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from apps.api.deps import AppSettings, CurrentUser, DbSession
from apps.api.llm import get_llm_provider
from apps.api.settings import Settings
from core.apps import account, actions, glance, money
from infrastructure.database.audit import record_audit
from infrastructure.database.models import ToolAction
from integrations.composio.client import ComposioClient, ComposioError
from integrations.llm.base import LLMProvider

router = APIRouter(prefix="/apps", tags=["apps"])

WHERE_IT_LIVES = (
    "A conexão fica guardada no Composio, não no Visão. O que ele lê e o que você aprovar passa "
    "por lá e fica no registro deles por até um ano."
)
WAIT_SECONDS = 120


class ActionOut(BaseModel):
    id: uuid.UUID
    toolkit: str
    tool: str
    version: str
    summary: str
    app: str
    tool_name: str
    description: str
    arguments: dict
    status: str
    result: str
    conversation_id: uuid.UUID | None
    created_at: datetime
    # A payment (core/apps/money.py): amount, currency and recipient, shown big on the card; the
    # approval must confirm the amount.
    money: dict[str, str] | None = None


class ConnectedOut(BaseModel):
    toolkit: str
    name: str
    logo: str = ""
    # "Olhar sozinho" (core/apps/glance.py): the read it runs every few hours, or "" when off.
    glance: str = ""
    # "Pagamentos": the daily ceiling when on; payment_app says whether to offer the switch.
    payments: dict[str, str] | None = None
    payment_app: bool = False


class PaymentsIn(BaseModel):
    enabled: bool
    cap: str = ""
    currency: str = money.DEFAULT_CURRENCY


class GlanceIn(BaseModel):
    enabled: bool


class GlanceOut(BaseModel):
    enabled: bool
    tool_name: str = ""


class AppsOut(BaseModel):
    enabled: bool
    notice: str = WHERE_IT_LIVES
    connected: list[ConnectedOut] = []
    problem: str = ""
    calls_this_month: int = 0
    monthly_limit: int = 0
    pending: list[ActionOut] = []


class CatalogItemOut(BaseModel):
    slug: str
    name: str
    description: str
    logo: str
    categories: list[str]
    # Connects with Composio's own sign-in.
    managed: bool
    # Can be connected from here: Composio's own sign-in, the app's self-registering sign-in, or
    # the owner's key for the app typed on Composio's page (docs/APPS.md).
    connectable: bool
    # Composio's page will ask for the owner's key to this app.
    asks_key: bool


class ConnectOut(BaseModel):
    connection_id: str
    url: str


def _apps(settings: Settings) -> ComposioClient | None:
    key = settings.composio_api_key
    return account.client(key.get_secret_value() if key else None)


def _required(settings: Settings) -> ComposioClient:
    apps = _apps(settings)
    if apps is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Os apps estão desligados neste servidor.")
    return apps


def _action(a: ToolAction) -> ActionOut:
    return ActionOut(
        id=a.id,
        toolkit=a.toolkit,
        tool=a.tool_slug,
        version=a.tool_version,
        summary=actions.describe(a),
        app=str(a.payload.get("app") or a.toolkit),
        tool_name=str(a.payload.get("tool_name") or a.tool_slug),
        description=str(a.payload.get("description") or ""),
        arguments=a.payload.get("arguments") or {},
        status=a.status,
        result=a.result,
        conversation_id=a.conversation_id,
        created_at=a.created_at,
        money=a.payload.get("money"),
    )


def _scheme(apps: ComposioClient, toolkit: str) -> str:
    found = next((t for t in apps.catalog() if t.slug == toolkit), None)
    return found.owner_scheme if found else ""


def _catalog(apps: ComposioClient) -> dict[str, CatalogItemOut]:
    try:
        found = apps.catalog()
    except ComposioError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"O Composio não respondeu: {exc}"
        ) from exc
    return {
        t.slug: CatalogItemOut(
            slug=t.slug,
            name=t.name,
            description=t.description,
            logo=t.logo,
            categories=list(t.categories),
            managed=t.managed,
            connectable=t.connectable,
            asks_key=t.asks_key,
        )
        for t in found
        if t.slug not in account.HIDDEN
    }


@router.get("")
def read_apps(db: DbSession, user: CurrentUser, settings: AppSettings) -> AppsOut:
    apps = _apps(settings)
    if apps is None:
        return AppsOut(enabled=False)
    ref = account.user_ref(user.id, settings.secret_key)
    problem = ""
    try:
        connections = [c for c in apps.connections(ref) if c.toolkit not in account.HIDDEN]
    except ComposioError as exc:
        connections, problem = [], f"O Composio não respondeu: {exc}."
    try:
        names = {t.slug: t for t in apps.catalog()}
    except ComposioError:
        names = {}
    seen = dict.fromkeys(c.toolkit for c in connections)
    looking = glance.chosen(user)
    paying = money.allowed(user)
    return AppsOut(
        enabled=True,
        connected=[
            ConnectedOut(
                toolkit=slug,
                name=names[slug].name if slug in names else slug.title(),
                logo=names[slug].logo if slug in names else "",
                glance=str((looking.get(slug) or {}).get("name") or ""),
                payments=paying.get(slug),
                payment_app=money.payment_app(
                    slug, names[slug].categories if slug in names else ()
                ),
            )
            for slug in seen
        ],
        problem=problem,
        calls_this_month=account.calls_this_month(db),
        monthly_limit=settings.composio_monthly_calls,
        pending=[_action(a) for a in actions.pending(db, user.id)],
    )


@router.get("/catalog")
def catalog(user: CurrentUser, settings: AppSettings) -> list[CatalogItemOut]:
    return list(_catalog(_required(settings)).values())


@router.post("/{toolkit}/connect")
def connect(toolkit: str, db: DbSession, user: CurrentUser, settings: AppSettings) -> ConnectOut:
    """Starts a connection: the app opens the returned page, then calls /wait."""
    apps = _required(settings)
    known = _catalog(apps)
    if toolkit not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "App não encontrado.")
    if not known[toolkit].connectable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Esse app pede um app OAuth próprio no Composio; ainda não dá para conectar daqui.",
        )
    scheme = "" if known[toolkit].managed else _scheme(apps, toolkit)
    try:
        connection_id, url = apps.start_connection(
            account.user_ref(user.id, settings.secret_key), toolkit, scheme
        )
    except ComposioError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"O Composio recusou: {exc}") from exc
    if not url.startswith("https://"):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "O Composio não deu a página de conexão.")
    record_audit(db, "apps.connect", "started", actor_user_id=user.id, details={"toolkit": toolkit})
    db.commit()
    return ConnectOut(connection_id=connection_id, url=url)


@router.post("/{toolkit}/glance")
def set_glance(
    toolkit: str,
    body: GlanceIn,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: Annotated[LLMProvider | None, Depends(get_llm_provider)],
) -> GlanceOut:
    """ "Olhar sozinho" for one connected app. On: one call picks the read it will run, shown back
    to the owner. Off: nothing is looked at again."""
    if not body.enabled:
        glance.turn_off(user, toolkit)
        record_audit(db, "apps.glance", "off", actor_user_id=user.id, details={"toolkit": toolkit})
        db.commit()
        return GlanceOut(enabled=False)
    apps = _required(settings)
    ref = account.user_ref(user.id, settings.secret_key)
    try:
        connected = {c.toolkit for c in apps.connections(ref)}
    except ComposioError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"O Composio não respondeu: {exc}"
        ) from exc
    if toolkit not in connected:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esse app não está conectado.")
    name = account.names(apps, [toolkit]).get(toolkit, toolkit)
    try:
        choice = glance.choose(
            db, user, provider=provider, apps=apps, toolkit=toolkit, app_name=name
        )
    except glance.GlanceError as exc:
        db.commit()  # the model call is still counted
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    record_audit(
        db,
        "apps.glance",
        "on",
        actor_user_id=user.id,
        details={"toolkit": toolkit, "tool": choice.tool},
    )
    db.commit()
    return GlanceOut(enabled=True, tool_name=choice.tool_name)


@router.post("/{toolkit}/payments")
def set_payments(
    toolkit: str, body: PaymentsIn, db: DbSession, user: CurrentUser, settings: AppSettings
) -> AppsOut:
    """ "Pagamentos" for one app: off by default, on only with a daily ceiling
    (core/apps/money.py)."""
    if not body.enabled:
        money.set_allowed(user, toolkit, None)
        record_audit(
            db, "apps.payments", "off", actor_user_id=user.id, details={"toolkit": toolkit}
        )
        db.commit()
        return read_apps(db, user, settings)
    try:
        cap = Decimal(body.cap.replace(",", ".").strip())
    except InvalidOperation as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Teto inválido.") from exc
    if not cap.is_finite() or cap <= 0 or cap > money.MAX_CAP:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"O teto por dia vai de 0,01 a {money.MAX_CAP}.",
        )
    apps = _required(settings)
    ref = account.user_ref(user.id, settings.secret_key)
    if toolkit not in {c.toolkit for c in account.connected(apps, ref, fresh=True)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esse app não está conectado.")
    currency = (body.currency or money.DEFAULT_CURRENCY).strip().upper()
    if not currency.isalpha() or not 3 <= len(currency) <= 4:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Moeda inválida.")
    money.set_allowed(user, toolkit, cap, currency)
    record_audit(
        db,
        "apps.payments",
        "on",
        actor_user_id=user.id,
        details={"toolkit": toolkit, "cap": str(cap), "currency": currency},
    )
    db.commit()
    return read_apps(db, user, settings)


@router.post("/connections/{connection_id}/wait")
def wait(
    connection_id: str,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    timeout: float = Query(default=WAIT_SECONDS, gt=0, le=WAIT_SECONDS),
) -> AppsOut:
    """Waits while the owner signs in to the app on Composio's page; no public callback."""
    apps = _required(settings)
    ref = account.user_ref(user.id, settings.secret_key)
    try:
        done = apps.wait_for_connection(connection_id, timeout=timeout)
    except ComposioError as exc:
        code = status.HTTP_408_REQUEST_TIMEOUT if exc.kind == "timeout" else 502
        raise HTTPException(code, f"A conexão não terminou: {exc}") from exc
    account.forget(ref)
    # Only one of this owner's: a connection id from anyone else does not count here.
    mine = {c.id for c in account.connected(apps, ref, fresh=True)}
    if done.id not in mine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexão não encontrada.")
    record_audit(
        db, "apps.connect", "success", actor_user_id=user.id, details={"toolkit": done.toolkit}
    )
    db.commit()
    return read_apps(db, user, settings)


@router.delete("/{toolkit}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(toolkit: str, db: DbSession, user: CurrentUser, settings: AppSettings) -> None:
    """Revokes and deletes the connection on Composio, and turns down what waited from it."""
    apps = _required(settings)
    ref = account.user_ref(user.id, settings.secret_key)
    try:
        mine = [c for c in apps.connections(ref) if c.toolkit == toolkit]
        for connection in mine:
            apps.disconnect(connection.id)
    except ComposioError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"O Composio não respondeu: {exc}"
        ) from exc
    account.forget(ref)
    actions.reject_app(db, user.id, toolkit)
    record_audit(
        db, "apps.disconnect", "success", actor_user_id=user.id, details={"toolkit": toolkit}
    )
    db.commit()


@router.get("/actions")
def list_actions(db: DbSession, user: CurrentUser) -> list[ActionOut]:
    return [_action(a) for a in actions.pending(db, user.id)]


@router.post("/actions/{action_id}/{decision}")
def decide(
    action_id: uuid.UUID,
    decision: str,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    via: Literal["toque", "voz"] = "toque",
    confirm_amount: str | None = Query(default=None, max_length=32),
) -> ActionOut:
    """`via=voz`: said in a call after it read the change aloud (docs/VOICE.md); recorded."""
    try:
        if decision == "approve":
            action = actions.approve(
                db,
                user,
                action_id,
                apps=_apps(settings),
                secret_key=settings.secret_key,
                monthly_limit=settings.composio_monthly_calls,
                via=via,
                confirm_amount=confirm_amount,
            )
        elif decision == "reject":
            action = actions.reject(db, user.id, action_id)
        else:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "decisão desconhecida")
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pedido não encontrado") from exc
    record_audit(
        db,
        f"apps.{decision}",
        "success",
        actor_user_id=user.id,
        details={"via": via, "toolkit": action.toolkit},
    )
    db.commit()
    return _action(action)
