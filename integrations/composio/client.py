"""The owner's other apps through Composio (docs/APPS.md, ADR-0028). The only place that imports
the `composio` SDK.

Composio keeps each app's connection (its tokens never pass through the Visão) and runs every
tool call on its servers. Here: the catalog of apps, connecting one (a link the owner opens, then
a wait, so no public callback address is needed), the tools of an app with their read and write
hints, running one tool at a pinned version, and undoing a connection (revoke, then delete).

Everything a tool returns is untrusted third-party text. Deciding what may run without the
owner's yes is not done here (core/apps/assist.py and core/apps/actions.py), except one guard:
a tool marked destructive is never executed by this client.
"""

import contextvars
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import httpx

TIMEOUT_SECONDS = 20.0
CATALOG_TTL_SECONDS = 6 * 3600
TOOLS_TTL_SECONDS = 600
MAX_TOOLS = 2000
# The hints Composio puts in a tool's tags (docs.composio.dev/docs/governance/tool-hints). Only
# "readOnlyHint" alone, among the ones that say what a tool changes, makes it a read.
READ_ONLY = "readOnlyHint"
DESTRUCTIVE = "destructiveHint"
# Hints that say nothing about whether a tool changes anything: it talks to the outside world
# (every app tool does), or calling it twice gives the same result. Composio marks its real reads
# with both, next to readOnlyHint (GITHUB_LIST_REPOSITORY_ISSUES, seen on 2026-11-25). Alone, or
# with a hint to create or update, they still leave a tool a write.
NEUTRAL_HINTS = frozenset({"openWorldHint", "idempotentHint"})
# Composio's tag for a toolkit's main tools; they go first when the list is cut.
IMPORTANT = "important"

# How the owner connects an app that has no sign-in of Composio's own, with nothing set up by the
# Visão: the app's own sign-in, which registers itself (DCR_OAUTH), or the owner's key for that
# app (API_KEY), typed on Composio's page. Both checked against the real Composio on 2026-11-25;
# the others (an OAuth app of our own, user and password) stay out.
OWNER_FILLED = ("DCR_OAUTH", "API_KEY")

T = TypeVar("T")


class ComposioError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def kind_of(tags: tuple[str, ...] | list[str]) -> str:
    """ "read", "write" or "destructive", from the tags alone. The hints are Composio's best
    effort, so any doubt is a write: no hint, a hint to create or update, an unknown hint, or
    read-only together with any of those. The neutral ones neither make nor break a read."""
    hints = {t for t in tags if isinstance(t, str) and t.endswith("Hint")} - NEUTRAL_HINTS
    if DESTRUCTIVE in hints:
        return "destructive"
    return "read" if hints == {READ_ONLY} else "write"


@dataclass(frozen=True)
class Toolkit:
    slug: str
    name: str
    description: str = ""
    logo: str = ""
    categories: tuple[str, ...] = ()
    # Connects with Composio's own OAuth app (one click).
    managed: bool = True
    # The app's sign-in methods as Composio names them (OAUTH2, API_KEY, DCR_OAUTH...).
    schemes: tuple[str, ...] = ()

    @property
    def owner_scheme(self) -> str:
        """Without Composio's own sign-in: the method the owner completes on Composio's page."""
        if self.managed:
            return ""
        return next((s for s in OWNER_FILLED if s in self.schemes), "")

    @property
    def connectable(self) -> bool:
        return self.managed or bool(self.owner_scheme)

    @property
    def asks_key(self) -> bool:
        """Composio's page asks the owner for their key to this app."""
        return self.owner_scheme == "API_KEY"


@dataclass(frozen=True)
class Connection:
    id: str
    toolkit: str
    status: str


@dataclass(frozen=True)
class Tool:
    slug: str
    name: str
    description: str
    toolkit: str
    version: str
    tags: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return kind_of(self.tags)


def _get(item: object, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _toolkit(item: object) -> Toolkit:
    meta = _get(item, "meta") or {}
    categories = tuple(str(_get(c, "name", "")) for c in (_get(meta, "categories") or []))
    return Toolkit(
        slug=str(_get(item, "slug", "")),
        name=str(_get(item, "name", "") or _get(item, "slug", "")),
        description=str(_get(meta, "description", "") or "")[:300],
        logo=str(_get(meta, "logo", "") or ""),
        categories=tuple(c for c in categories if c),
        managed=bool(_get(item, "composio_managed_auth_schemes") or _get(item, "no_auth")),
        schemes=tuple(str(s) for s in (_get(item, "auth_schemes") or [])),
    )


def _tool(item: object) -> Tool:
    toolkit = _get(item, "toolkit")
    return Tool(
        slug=str(_get(item, "slug", "")),
        name=str(_get(item, "name", "")),
        description=str(_get(item, "human_description") or _get(item, "description") or "")[:500],
        toolkit=str(_get(toolkit, "slug", "") if toolkit is not None else ""),
        version=str(_get(item, "version", "") or ""),
        tags=tuple(str(t) for t in (_get(item, "tags") or [])),
        parameters=dict(_get(item, "input_parameters") or {}),
    )


def _translate(exc: Exception) -> ComposioError:
    import composio_client
    from composio import exceptions as sdk

    if isinstance(exc, composio_client.RateLimitError):
        return ComposioError("rate_limited", "o limite de pedidos do Composio foi atingido")
    if isinstance(exc, composio_client.AuthenticationError | composio_client.PermissionDeniedError):
        return ComposioError("auth", "o Composio recusou a chave da API")
    if isinstance(exc, composio_client.NotFoundError):
        return ComposioError("not_found", "o Composio não achou isso")
    if isinstance(exc, composio_client.APITimeoutError | sdk.ComposioSDKTimeoutError):
        return ComposioError("timeout", "o Composio demorou demais")
    if isinstance(exc, composio_client.APIConnectionError | httpx.HTTPError):
        return ComposioError("network", "o Composio não respondeu")
    if isinstance(exc, composio_client.APIStatusError):
        return ComposioError(f"http_{exc.status_code}", "o Composio devolveu um erro")
    return ComposioError("failed", "o Composio devolveu um erro")


class ComposioClient:
    def __init__(
        self, api_key: str, *, http: httpx.Client | None = None, timeout: float = TIMEOUT_SECONDS
    ) -> None:
        self._api_key = api_key
        self._http = http or httpx.Client(timeout=timeout)
        self._timeout = timeout
        self._sdk: Any = None
        self._catalog: tuple[float, list[Toolkit]] | None = None
        self._tools: dict[str, tuple[float, list[Tool]]] = {}

    def _composio(self) -> Any:
        if self._sdk is None:
            from composio import Composio

            self._sdk = self._quiet(
                lambda: Composio(
                    api_key=self._api_key,
                    http_client=self._http,
                    timeout=int(self._timeout),
                    # A 429 is not retried within the turn (ADR-0028), nor anything else.
                    max_retries=0,
                    allow_tracking=False,
                )
            )
        return self._sdk

    @staticmethod
    def _quiet(call: Callable[[], T]) -> T:
        """Runs with the SDK's usage telemetry off. The switch is a context variable, so setting
        it once when the SDK is built would not cover calls from other request threads."""
        from composio.core.models.base import allow_tracking

        def run() -> T:
            allow_tracking.set(False)
            return call()

        return contextvars.copy_context().run(run)

    def _call(self, call: Callable[[Any], T]) -> T:
        try:
            return self._quiet(lambda: call(self._composio()))
        except ComposioError:
            raise
        except Exception as exc:  # noqa: BLE001 (every SDK failure is one ComposioError)
            raise _translate(exc) from exc

    # Apps ---------------------------------------------------------------------------------------

    def catalog(self) -> list[Toolkit]:
        """Every app Composio offers, most used first; kept for a few hours."""
        if self._catalog and time.monotonic() - self._catalog[0] < CATALOG_TTL_SECONDS:
            return self._catalog[1]
        found: list[Toolkit] = []
        cursor: str | None = None
        for _ in range(5):
            page = self._call(
                lambda c, cursor=cursor: c.toolkits.list(limit=1000, sort_by="usage", cursor=cursor)
            )
            found.extend(_toolkit(item) for item in (_get(page, "items") or []))
            cursor = _get(page, "next_cursor")
            if not cursor:
                break
        found = [t for t in found if t.slug]
        self._catalog = (time.monotonic(), found)
        return found

    def connections(self, user_id: str) -> list[Connection]:
        page = self._call(
            lambda c: c.connected_accounts.list(user_ids=[user_id], statuses=["ACTIVE"])
        )
        return [
            Connection(
                id=str(_get(item, "id", "")),
                toolkit=str(_get(_get(item, "toolkit"), "slug", "")),
                status=str(_get(item, "status", "")),
            )
            for item in (_get(page, "items") or [])
        ]

    def start_connection(self, user_id: str, toolkit: str, scheme: str = "") -> tuple[str, str]:
        """(connection id, the page where the owner signs in to the app). `scheme` empty: with
        Composio's own sign-in; else one of OWNER_FILLED, set up with no credentials so that
        Composio's page asks the owner for what is missing."""
        if scheme and scheme not in OWNER_FILLED:
            raise ComposioError("refused", "esse jeito de conectar ainda não é aceito")

        def start(c: Any) -> tuple[str, str]:
            configs = _get(c.auth_configs.list(toolkit_slug=toolkit), "items") or []
            enabled = [a for a in configs if _get(a, "status", "ENABLED") == "ENABLED"]
            if enabled:
                newest = sorted(enabled, key=lambda a: str(_get(a, "created_at") or ""))[-1]
                config_id = str(_get(newest, "id"))
            else:
                options: dict[str, Any] = (
                    {
                        "type": "use_custom_auth",
                        "auth_scheme": scheme,
                        "name": f"visao-{toolkit}"[:60],
                        "credentials": {},
                    }
                    if scheme
                    else {"type": "use_composio_managed_auth"}
                )
                config_id = str(_get(c.auth_configs.create(toolkit, options), "id"))
            request = c.connected_accounts.link(user_id, config_id)
            return str(request.id), str(request.redirect_url or "")

        return self._call(start)

    def wait_for_connection(self, connection_id: str, timeout: float) -> Connection:
        account = self._call(
            lambda c: c.connected_accounts.wait_for_connection(connection_id, timeout=timeout)
        )
        return Connection(
            id=str(_get(account, "id", connection_id)),
            toolkit=str(_get(_get(account, "toolkit"), "slug", "")),
            status=str(_get(account, "status", "")),
        )

    def disconnect(self, connection_id: str) -> None:
        """Revoke (best effort: some apps cannot be revoked from outside), then delete for good."""
        from composio import exceptions as sdk

        def undo(c: Any) -> None:
            try:
                c.connected_accounts.revoke(connection_id)
            except (
                sdk.ComposioConnectedAccountRevocationNotSupportedError,
                sdk.ComposioConnectedAccountNotRevokableError,
            ):
                pass
            c.connected_accounts.delete(connection_id)

        self._call(undo)

    # Tools --------------------------------------------------------------------------------------

    def tools(self, toolkit: str) -> list[Tool]:
        """The app's tools at their current version, hints included; kept for a few minutes."""
        kept = self._tools.get(toolkit)
        if kept and time.monotonic() - kept[0] < TOOLS_TTL_SECONDS:
            return kept[1]
        # All of them: GitHub has about 900, and listing its issues was number 633.
        items = self._call(
            lambda c: c.tools.get_raw_composio_tools(toolkits=[toolkit], limit=MAX_TOOLS)
        )
        found = [_tool(item) for item in items]
        found = [t for t in found if t.slug and t.version and t.toolkit == toolkit]
        self._tools[toolkit] = (time.monotonic(), found)
        return found

    def execute(self, user_id: str, tool: Tool, arguments: dict[str, Any]) -> Any:
        """Runs one tool at the version it was listed with. Never a destructive one."""
        if tool.kind == "destructive":
            raise ComposioError("refused", "apagar pelos apps está desligado")
        if not tool.version or tool.version == "latest":
            raise ComposioError("refused", "ferramenta sem versão fixada")
        out = self._call(
            lambda c: c.tools.execute(
                tool.slug, dict(arguments), user_id=user_id, version=tool.version
            )
        )
        if not _get(out, "successful", False):
            error = str(_get(out, "error") or "a ferramenta falhou")[:200]
            raise ComposioError("failed", error)
        return _get(out, "data")
