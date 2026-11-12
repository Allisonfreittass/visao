"""Reads a GitHub repository the owner sends, through the REST API at one fixed host.

Public repositories need no key (60 requests an hour per server). A read-only token
(VISION_GITHUB_TOKEN) raises that and opens the owner's private repositories. Everything that comes
back is untrusted text and only ever reaches the model as data.
"""

import base64
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

API = "https://api.github.com"
USER_AGENT = "VISAO-reader/0.1 (personal assistant)"
MAX_FILE_CHARS = 4000
MAX_README_CHARS = 5000
MAX_TREE_PATHS = 150
# Files that say the most about a project in the fewest bytes.
KEY_FILES = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "composer.json",
    "Gemfile",
    "Dockerfile",
    "docker-compose.yml",
)
MAX_KEY_FILES = 3
_NAME = r"[A-Za-z0-9_.-]{1,100}"
_URL = re.compile(
    rf"^https://(?:www\.)?github\.com/(?P<owner>{_NAME})/(?P<repo>{_NAME})"
    rf"(?:/(?P<kind>tree|blob)/(?P<ref>[^/\s]{{1,100}})(?:/(?P<path>[^\s?#]*))?)?/?(?:[?#].*)?$"
)
_NOT_REPOS = {"orgs", "settings", "marketplace", "explore", "topics", "features", "login", "about"}


class GitHubError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str
    ref: str | None = None
    path: str | None = None
    is_file: bool = False

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


def parse(url: str) -> RepoRef | None:
    match = _URL.match(url.strip())
    if not match or match["owner"].lower() in _NOT_REPOS:
        return None
    repo = match["repo"].removesuffix(".git")
    return RepoRef(
        owner=match["owner"],
        repo=repo,
        ref=match["ref"],
        path=(match["path"] or "").strip("/") or None,
        is_file=match["kind"] == "blob",
    )


@dataclass
class Repo:
    ref: RepoRef
    description: str = ""
    language: str = ""
    languages: dict[str, int] = field(default_factory=dict)
    stars: int = 0
    default_branch: str = ""
    pushed_at: str = ""
    private: bool = False
    readme: str = ""
    tree: list[str] = field(default_factory=list)
    tree_truncated: bool = False
    commits: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)

    def as_text(self) -> str:
        lines = [f"Repositório {self.ref.owner}/{self.ref.repo} ({self.ref.url})"]
        facts = [
            self.description,
            f"linguagem principal: {self.language}" if self.language else "",
            "linguagens: " + ", ".join(self.languages) if self.languages else "",
            f"{self.stars} estrelas",
            f"último push: {self.pushed_at}" if self.pushed_at else "",
            "privado" if self.private else "público",
        ]
        lines.append("; ".join(f for f in facts if f))
        if self.commits:
            lines.append("Últimos commits: " + " | ".join(self.commits))
        if self.tree:
            more = " (lista cortada)" if self.tree_truncated else ""
            lines.append(f"Arquivos{more}: " + ", ".join(self.tree))
        if self.readme:
            lines.append("README:\n" + self.readme)
        for path, text in self.files.items():
            lines.append(f"Arquivo {path}:\n{text}")
        return "\n".join(lines)


class GitHubReader:
    def __init__(self, token: str | None = None, client: httpx.Client | None = None) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(base_url=API, timeout=8.0, headers=headers)
        if client is not None:
            self._client.headers.update(headers)

    def _get(self, path: str, **params) -> object:
        try:
            response = self._client.get(path, params=params or None)
        except httpx.HTTPError as exc:
            raise GitHubError("network", f"GitHub não respondeu: {type(exc).__name__}") from exc
        if response.status_code == 404:
            raise GitHubError("not_found", "repositório não encontrado ou privado")
        if response.status_code in (403, 429):
            raise GitHubError("rate_limited", "limite de leitura do GitHub atingido")
        if response.status_code != 200:
            raise GitHubError(f"http_{response.status_code}", "GitHub devolveu um erro")
        return response.json()

    def _optional(self, path: str, **params) -> object | None:
        try:
            return self._get(path, **params)
        except GitHubError:
            return None

    def _file(self, base: str, path: str, ref: str) -> str | None:
        data = self._optional(f"{base}/contents/{quote(path)}", ref=ref)
        if not isinstance(data, dict) or data.get("type") != "file":
            return None
        raw = data.get("content") or ""
        try:
            text = base64.b64decode(raw).decode("utf-8", "replace")
        except ValueError:
            return None
        return text[:MAX_FILE_CHARS]

    def read(self, ref: RepoRef) -> Repo:
        base = f"/repos/{ref.owner}/{ref.repo}"
        info = self._get(base)
        if not isinstance(info, dict):
            raise GitHubError("bad_response", "resposta inesperada do GitHub")
        branch = ref.ref or str(info.get("default_branch") or "main")
        repo = Repo(
            ref=ref,
            description=str(info.get("description") or "")[:300],
            language=str(info.get("language") or ""),
            stars=int(info.get("stargazers_count") or 0),
            default_branch=str(info.get("default_branch") or ""),
            pushed_at=str(info.get("pushed_at") or ""),
            private=bool(info.get("private")),
        )
        with ThreadPoolExecutor(max_workers=4) as pool:
            languages = pool.submit(self._optional, f"{base}/languages")
            readme = pool.submit(self._optional, f"{base}/readme", ref=branch)
            tree = pool.submit(self._optional, f"{base}/git/trees/{quote(branch)}", recursive="1")
            commits = pool.submit(self._optional, f"{base}/commits", sha=branch, per_page="5")
        if isinstance(languages.result(), dict):
            repo.languages = dict(list(languages.result().items())[:6])
        readme_data = readme.result()
        if isinstance(readme_data, dict) and readme_data.get("content"):
            try:
                text = base64.b64decode(readme_data["content"]).decode("utf-8", "replace")
                repo.readme = text[:MAX_README_CHARS]
            except ValueError:
                pass
        paths: list[str] = []
        tree_data = tree.result()
        if isinstance(tree_data, dict):
            paths = [
                str(item.get("path"))
                for item in tree_data.get("tree", [])
                if isinstance(item, dict) and item.get("type") == "blob"
            ]
            repo.tree_truncated = bool(tree_data.get("truncated")) or len(paths) > MAX_TREE_PATHS
            if ref.path and not ref.is_file:
                paths = [p for p in paths if p.startswith(ref.path + "/")] or paths
            repo.tree = paths[:MAX_TREE_PATHS]
        commit_data = commits.result()
        if isinstance(commit_data, list):
            for item in commit_data[:5]:
                commit = item.get("commit", {}) if isinstance(item, dict) else {}
                message = str(commit.get("message") or "").splitlines()[0:1]
                date = str((commit.get("author") or {}).get("date") or "")[:10]
                if message:
                    repo.commits.append(f"{date} {message[0][:120]}".strip())
        wanted = [ref.path] if ref.is_file and ref.path else []
        wanted += [p for p in KEY_FILES if p in paths][: MAX_KEY_FILES - len(wanted)]
        if wanted:
            with ThreadPoolExecutor(max_workers=3) as pool:
                found = list(pool.map(lambda p: (p, self._file(base, p, branch)), wanted))
            repo.files = {p: text for p, text in found if text}
        return repo
