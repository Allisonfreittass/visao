"""25/11/2026: "Quantos commits foram feitos hoje no repositório Visao?" became a Mac task that
never ran with the Mac off. GitHub is read on the server now: the number reaches the reply in the
same turn, with no question back and no Mac."""

from dataclasses import replace
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from core.decision.pipeline import run_turn
from core.identity.genesis import get_identity
from infrastructure.database.models import ArmTask
from integrations.github.api import GitHubAPI
from tests.fakes import FakeLLMProvider
from tests.integration.test_mind import setup
from tests.integration.test_mind_temperament import chat, mac
from tests.integration.test_phase9 import CONFIG


def github(count: int) -> GitHubAPI:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/Allisonfreittass/visao/commits"
        return httpx.Response(
            200,
            json=[
                {
                    "sha": f"{i:07d}ff",
                    "commit": {
                        "message": f"Commit {i}",
                        "author": {"date": datetime.now(UTC).isoformat()},
                    },
                }
                for i in range(count)
            ],
        )

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    return GitHubAPI("tok", client=client)


def test_commits_today_with_the_mac_off_come_from_the_server(db):
    owner = setup(db)
    mac(db, owner, ["visao"])  # paired, last seen long ago: off
    provider = FakeLLMProvider(reply_text="Hoje foram 3 commits no visao.")
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="quantos commits teve hoje no visao?",
        provider=provider,
        search=None,
        config=CONFIG,
        github=github(3),
    )
    assert "github_read" in outcome.plan.executed()
    assert db.scalar(select(ArmTask)) is None
    # One model call: the reply. No Mac extraction, no curiosity assessment in between.
    assert len(provider.prompts) == 1
    system = provider.prompts[0][0].content
    assert "Commits em Allisonfreittass/visao (branch principal) hoje" in system
    assert ": 3." in system and "sem perguntar qual repositório" in system


def test_a_message_without_github_never_reads_it(db):
    owner = setup(db)
    outcome = run_turn(
        db,
        conversation=chat(db, owner),
        identity=get_identity(db),
        owner=owner,
        text="bom dia",
        provider=FakeLLMProvider(),
        search=None,
        config=replace(CONFIG, curiosity_enabled=False),
        github=github(0),
    )
    assert not any(a.startswith("github") for a in outcome.plan.executed())
