"""Reading a GitHub question in code: the owner's nicknames for this project resolve to it without
a question back, and "hoje" is the owner's day, not the server's."""

from datetime import UTC, datetime

import httpx
import pytest

from core.github import repos
from core.github.assist import run
from integrations.github.api import GitHubAPI

DEFAULT = "Allisonfreittass/visao"


@pytest.mark.parametrize(
    "text",
    [
        "quantos commits teve hoje no visao?",
        "e no visão, quantos commits?",
        "quais PRs abertos tem o do visao",
        "issues abertas do meu assistente",
        "quantos commits teve no seu repositório essa semana?",
        "quantos commits teve hoje?",  # no repository named: the default one
    ],
)
def test_nicknames_and_silence_resolve_to_the_default_repo(text):
    assert repos.resolve(text) == DEFAULT


def test_an_explicit_repo_or_another_known_one_wins():
    assert repos.resolve("commits de octocat/hello-world hoje") == "octocat/hello-world"
    known = ("Allisonfreittass/visao", "Allisonfreittass/mercado")
    assert repos.resolve("quantos commits no mercado ontem?", known) == "Allisonfreittass/mercado"
    # A date is not a repository.
    assert repos.resolve("commits desde 25/11", known) == DEFAULT
    # A nickname beats a repository with a similar name.
    assert repos.resolve("commits do visao", ("Allisonfreittass/visao-old",)) == DEFAULT


def test_what_is_asked_and_what_is_a_change():
    assert repos.kinds("quantos commits teve hoje no visao?") == (repos.COMMITS,)
    assert repos.kinds("tem PR aberto? e issues?") == (repos.PULLS, repos.ISSUES)
    assert repos.kinds("lista meus repositórios") == (repos.REPOS,)
    # Changing GitHub is not a read: it goes to the apps or the Mac, with the owner's tap.
    assert repos.kinds("faz commit disso no visao") == ()
    assert repos.kinds("cria uma issue pro bug do login") == ()
    assert repos.kinds("roda os testes do visao") == ()


def test_today_is_the_owners_day():
    # 01:30 UTC on the 26th is still the 25th in São Paulo.
    now = datetime(2026, 11, 26, 1, 30, tzinfo=UTC)
    today = repos.period("quantos commits hoje?", now, "America/Sao_Paulo")
    assert today.since.isoformat() == "2026-11-25T00:00:00-03:00"
    assert today.words == "hoje"
    yesterday = repos.period("e ontem?", now, "America/Sao_Paulo")
    assert (yesterday.since.day, yesterday.until.day) == (24, 25)
    assert repos.period("nos últimos 3 dias", now, "UTC").words == "nos últimos 3 dias"
    assert repos.period("quantos commits?", now, "UTC").words == "nos últimos 7 dias"


def github(handler) -> GitHubAPI:
    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    return GitHubAPI("tok", client=client)


def commit(n: int) -> dict:
    return {
        "sha": f"{n:07d}abc",
        "commit": {"message": f"Mudança {n}\n\ncorpo", "author": {"date": "2026-11-25T15:00:00Z"}},
        "author": {"login": "Allisonfreittass"},
    }


def test_commits_today_are_counted_on_the_server():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json=[commit(i) for i in range(5)])

    now = datetime(2026, 11, 25, 18, 0, tzinfo=UTC)
    done = run("quantos commits teve hoje no visao?", api=github(handler), now=now, timezone="UTC")
    assert done is not None and done.read == [repos.COMMITS]
    assert "Commits em Allisonfreittass/visao (branch principal) hoje" in done.block
    assert ": 5." in done.block and "Mudança 0" in done.block
    assert seen[0].url.path == "/repos/Allisonfreittass/visao/commits"
    assert seen[0].url.params["since"] == "2026-11-25T00:00:00+00:00"


def test_a_failure_says_what_to_configure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    done = run(
        "issues abertas do visao",
        api=GitHubAPI(None, client=client),
        now=datetime.now(UTC),
        timezone="UTC",
    )
    assert done is not None and not done.read
    assert "VISION_GITHUB_TOKEN" in done.block


def test_a_message_without_github_does_nothing():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no call")

    assert run("bom dia", api=github(handler), now=datetime.now(UTC), timezone="UTC") is None


def test_a_rate_limit_without_a_token_says_to_set_one_and_never_blames_the_mac():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "API rate limit exceeded"})

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    done = run(
        "quantos commits teve hoje no visao?",
        api=GitHubAPI(None, client=client),
        now=datetime.now(UTC),
        timezone="UTC",
    )
    assert done is not None and not done.read
    assert "60 leituras por hora" in done.block and "VISION_GITHUB_TOKEN" in done.block
    assert "não fale do Mac" in done.block
