"""The Composio API answered from recorded responses (tests/fixtures/composio), with no network.

The responses follow the shapes of composio-client 2.1.36 (the one composio 0.35.0 pins); they
were written from its response types, since there was no key yet to record them live. Any request
the table does not know fails the test instead of leaving the machine."""

import json
from pathlib import Path

import httpx

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "composio"
API = "/api/v3.1"


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class RecordedComposio:
    """An httpx transport handler. `requests` keeps every request, `answers` can be replaced."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.answers: dict[tuple[str, str], object] = {
            ("GET", f"{API}/toolkits"): recorded("toolkits"),
            ("GET", f"{API}/tools"): recorded("tools_github"),
            ("POST", f"{API}/tools/execute/GITHUB_LIST_REPOSITORY_ISSUES"): recorded(
                "execute_list_issues"
            ),
            ("POST", f"{API}/tools/execute/GITHUB_GET_AN_ISSUE"): recorded("execute_list_issues"),
            ("POST", f"{API}/tools/execute/GITHUB_CREATE_AN_ISSUE"): recorded(
                "execute_create_issue"
            ),
            ("POST", f"{API}/tools/execute/GITHUB_UPDATE_AN_ISSUE"): recorded(
                "execute_create_issue"
            ),
            ("POST", f"{API}/tools/execute/GITHUB_STAR_A_REPOSITORY"): recorded(
                "execute_create_issue"
            ),
            ("GET", f"{API}/auth_configs"): recorded("auth_configs_github"),
            ("POST", f"{API}/connected_accounts/link"): recorded("link_create"),
            ("GET", f"{API}/connected_accounts"): {
                "items": [],
                "current_page": 1,
                "total_items": 0,
                "total_pages": 1,
            },
            ("GET", f"{API}/connected_accounts/ca_github1"): recorded("connected_account_active"),
            ("POST", f"{API}/connected_accounts/ca_github1/revoke"): recorded("revoke"),
            ("DELETE", f"{API}/connected_accounts/ca_github1"): recorded("delete"),
        }
        tools = recorded("tools_github")["items"]
        for tool in tools:
            self.answers[("GET", f"{API}/tools/{tool['slug']}")] = tool

    def connected(self) -> None:
        """From now on the owner's GitHub shows as connected."""
        self.answers[("GET", f"{API}/connected_accounts")] = recorded("connected_accounts")

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.get((request.method, request.url.path))
        if answer is None:
            raise AssertionError(f"pedido não gravado: {request.method} {request.url}")
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer)

    def sent(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and r.url.path == f"{API}{path}"]

    def http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))
