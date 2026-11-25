"""What the Composio SDK (composio 0.35.0) really does, checked without network (ADR-0028, step 1).

The ADR left three things open: where the read/write hints come from, how a tool's version is
pinned, and how the key is passed. The answers, as these tests show:

- The hints come in each tool's `tags` (a list of strings such as "readOnlyHint", "createHint"),
  next to other tags like "openWorldHint" or a category. They are not a separate field.
- `Composio(api_key=...)` exists and the key goes as the `x-api-key` header; the environment
  variable COMPOSIO_API_KEY is only the fallback when the argument is left out.
- A version is pinned per execution (`version=...` goes in the request body). Listing always
  asks for `toolkit_versions=latest` and each tool comes with its current `version`; executing
  without a version means "latest", which the SDK refuses on purpose.
- Usage telemetry goes to telemetry.composio.dev unless `allow_tracking=False`. That switch is a
  context variable: set at construction it covers only that thread or context, so
  integrations/composio/client.py turns it off around every call.
"""

import contextvars
import json

import httpx
import pytest

pytest.importorskip("composio")

from composio import Composio  # noqa: E402
from composio.core.models import _telemetry  # noqa: E402
from composio.exceptions import ToolVersionRequiredError  # noqa: E402

from tests.fake_composio import API, RecordedComposio  # noqa: E402


def sdk(api: RecordedComposio, **kwargs) -> Composio:
    return Composio(
        api_key="chave-de-teste", http_client=api.http(), max_retries=0, timeout=20, **kwargs
    )


def test_the_hints_are_in_each_tools_tags():
    api = RecordedComposio()
    tools = sdk(api, allow_tracking=False).tools.get_raw_composio_tools(
        toolkits=["github"], limit=100
    )
    tags = {t.slug: list(t.tags) for t in tools}
    assert tags["GITHUB_LIST_REPOSITORY_ISSUES"] == [
        "important",
        "issues",
        "openWorldHint",
        "readOnlyHint",
        "idempotentHint",
    ]
    assert tags["GITHUB_CREATE_AN_ISSUE"] == ["createHint", "openWorldHint"]
    assert tags["GITHUB_STAR_A_REPOSITORY"] == []  # no hint at all
    assert all(t.version == "20251111_00" for t in tools)
    [listing] = api.sent("GET", "/tools")
    assert listing.url.params["toolkit_slug"] == "github"
    assert listing.url.params["toolkit_versions"] == "latest"


def test_the_key_is_an_argument_and_goes_as_a_header(monkeypatch):
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    api = RecordedComposio()
    sdk(api, allow_tracking=False).toolkits.list(limit=10)
    assert api.requests[0].headers["x-api-key"] == "chave-de-teste"
    assert api.requests[0].url.host == "backend.composio.dev"


def test_a_pinned_version_goes_with_the_execution_and_latest_is_refused():
    api = RecordedComposio()
    composio = sdk(api, allow_tracking=False)
    out = composio.tools.execute(
        "GITHUB_GET_AN_ISSUE",
        {"owner": "dono", "repo": "visao", "issue_number": 7},
        user_id="u-hmac",
        version="20251111_00",
    )
    assert out["successful"] is True and "log_id" not in out
    [sent] = api.sent("POST", "/tools/execute/GITHUB_GET_AN_ISSUE")
    body = json.loads(sent.content)
    assert body == {
        "user_id": "u-hmac",
        "version": "20251111_00",
        "arguments": {"owner": "dono", "repo": "visao", "issue_number": 7},
    }
    with pytest.raises(ToolVersionRequiredError):
        composio.tools.execute("GITHUB_GET_AN_ISSUE", {}, user_id="u-hmac")


def test_connecting_is_a_link_then_a_wait_with_no_public_callback():
    api = RecordedComposio()
    composio = sdk(api, allow_tracking=False)
    [config] = composio.auth_configs.list(toolkit_slug="github").items
    request = composio.connected_accounts.link("u-hmac", config.id)
    assert request.redirect_url.startswith("https://connect.composio.dev/")
    account = composio.connected_accounts.wait_for_connection(request.id, timeout=5)
    assert (account.id, account.status) == ("ca_github1", "ACTIVE")
    [link] = api.sent("POST", "/connected_accounts/link")
    assert json.loads(link.content) == {"auth_config_id": "ac_github", "user_id": "u-hmac"}


def test_undoing_is_revoke_then_delete():
    api = RecordedComposio()
    composio = sdk(api, allow_tracking=False)
    assert composio.connected_accounts.revoke("ca_github1").connected_account.status == "REVOKED"
    composio.connected_accounts.delete("ca_github1")
    assert [(r.method, r.url.path) for r in api.requests] == [
        ("POST", f"{API}/connected_accounts/ca_github1/revoke"),
        ("DELETE", f"{API}/connected_accounts/ca_github1"),
    ]


def test_telemetry_is_off_only_in_the_context_that_turned_it_off(monkeypatch):
    pushed = []
    monkeypatch.setattr(_telemetry, "push_event", pushed.append)
    from composio.core.models import base

    monkeypatch.setattr(base, "push_event", lambda event: pushed.append(event))
    api = RecordedComposio()
    composio = contextvars.Context().run(sdk, api, allow_tracking=False)
    # Called from another context, as a request thread would be: tracking is back on there.
    contextvars.Context().run(composio.tools.get_raw_composio_tools, toolkits=["github"])
    assert pushed, "a chamada fora do contexto mandaria telemetria"
    pushed.clear()

    def quiet():
        base.allow_tracking.set(False)
        composio.tools.get_raw_composio_tools(toolkits=["github"])

    contextvars.Context().run(quiet)
    assert pushed == []
    assert all(r.url.host != "telemetry.composio.dev" for r in api.requests)


def test_an_unknown_request_never_leaves_the_machine():
    api = RecordedComposio()
    api.answers.pop(("GET", f"{API}/toolkits"))
    with pytest.raises(AssertionError, match="pedido não gravado"):
        sdk(api, allow_tracking=False).toolkits.list()
    assert isinstance(api.requests[0], httpx.Request)
