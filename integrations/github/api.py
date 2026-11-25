"""The owner's GitHub, read from the server (Lightsail), never through the Mac.

Commits of a repository in a period, the owner's repositories, open pull requests and issues,
through the REST API at one fixed host. The token (VISION_GITHUB_TOKEN or GITHUB_TOKEN) is
optional: without it public repositories still answer, with the 60-an-hour limit. What comes back
is third-party text and only reaches the model as data.
"""

from dataclasses import dataclass
from datetime import datetime

import httpx

from integrations.github.reader import API, USER_AGENT, GitHubError

# Enough for "quantos commits hoje/esta semana" without paging forever: 5 pages of 100.
MAX_PAGES = 5
PER_PAGE = 100


@dataclass(frozen=True)
class Commit:
    sha: str
    message: str
    author: str
    date: str  # ISO 8601, as GitHub gives it (UTC)


@dataclass(frozen=True)
class RepoSummary:
    full_name: str
    private: bool
    pushed_at: str
    description: str


@dataclass(frozen=True)
class Item:
    """An open pull request or issue."""

    number: int
    title: str
    author: str
    url: str
    created_at: str


@dataclass(frozen=True)
class Commits:
    items: list[Commit]
    # True when there were more than MAX_PAGES * PER_PAGE: the count is "at least".
    capped: bool


class GitHubAPI:
    def __init__(
        self, token: str | None = None, client: httpx.Client | None = None, login: str = ""
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.has_token = bool(token)
        # Whose repositories "meus repos" lists without a token (with one, the token's owner).
        self.login = login
        self._client = client or httpx.Client(base_url=API, timeout=8.0, headers=headers)
        if client is not None:
            self._client.headers.update(headers)

    def _get(self, path: str, **params: str) -> object:
        try:
            response = self._client.get(path, params=params or None)
        except httpx.HTTPError as exc:
            raise GitHubError("network", f"GitHub não respondeu: {type(exc).__name__}") from exc
        if response.status_code == 401:
            raise GitHubError("unauthorized", "o token do GitHub foi recusado")
        if response.status_code == 404:
            raise GitHubError("not_found", "repositório não encontrado ou privado")
        if response.status_code in (403, 429):
            raise GitHubError("rate_limited", "limite de leitura do GitHub atingido")
        if response.status_code == 409:
            # An empty repository answers 409 to /commits.
            return []
        if response.status_code != 200:
            raise GitHubError(f"http_{response.status_code}", "GitHub devolveu um erro")
        return response.json()

    def _pages(self, path: str, **params: str) -> tuple[list[dict], bool]:
        found: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            data = self._get(path, per_page=str(PER_PAGE), page=str(page), **params)
            batch = [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
            found.extend(batch)
            if len(batch) < PER_PAGE:
                return found, False
        return found, True

    def commits(self, repo: str, since: datetime, until: datetime) -> Commits:
        """Commits on the default branch between since and until (aware datetimes)."""
        rows, capped = self._pages(
            f"/repos/{repo}/commits",
            since=since.isoformat(),
            until=until.isoformat(),
        )
        items = []
        for row in rows:
            commit = row.get("commit") or {}
            author = commit.get("author") or {}
            login = (row.get("author") or {}).get("login") if row.get("author") else None
            items.append(
                Commit(
                    sha=str(row.get("sha") or "")[:7],
                    message=(str(commit.get("message") or "").splitlines() or [""])[0][:120],
                    author=str(login or author.get("name") or ""),
                    date=str(author.get("date") or ""),
                )
            )
        return Commits(items, capped)

    def repos(self) -> list[RepoSummary]:
        """The owner's repositories, most recently pushed first."""
        if self.has_token:
            data = self._get("/user/repos", sort="pushed", per_page="50", affiliation="owner")
        elif self.login:
            data = self._get(f"/users/{self.login}/repos", sort="pushed", per_page="50")
        else:
            raise GitHubError("no_token", "sem token do GitHub")
        rows = [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
        return [
            RepoSummary(
                full_name=str(r.get("full_name") or ""),
                private=bool(r.get("private")),
                pushed_at=str(r.get("pushed_at") or ""),
                description=str(r.get("description") or "")[:160],
            )
            for r in rows
        ]

    def pulls(self, repo: str) -> list[Item]:
        data = self._get(f"/repos/{repo}/pulls", state="open", per_page="50")
        return [_item(d) for d in data if isinstance(d, dict)] if isinstance(data, list) else []

    def issues(self, repo: str) -> list[Item]:
        """Open issues, without the pull requests GitHub mixes into this list."""
        data = self._get(f"/repos/{repo}/issues", state="open", per_page="50")
        rows = data if isinstance(data, list) else []
        return [_item(d) for d in rows if isinstance(d, dict) and "pull_request" not in d]


def _item(row: dict) -> Item:
    return Item(
        number=int(row.get("number") or 0),
        title=str(row.get("title") or "")[:160],
        author=str((row.get("user") or {}).get("login") or ""),
        url=str(row.get("html_url") or ""),
        created_at=str(row.get("created_at") or ""),
    )
