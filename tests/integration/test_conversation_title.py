"""A short title after the first exchange, for the side menu (core/conversation/title.py)."""

from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from apps.worker.handlers import title_handler
from core.conversation import title
from core.identity.genesis import run_genesis
from infrastructure.database.models import ModelUsage, ScheduledJob
from infrastructure.jobs import queue
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login


def _world(client, db, named='"Viagem ao Chile em agosto."', fail=False):
    def respond(messages):
        if messages[0].content == title.INSTRUCTIONS:
            if fail:
                from integrations.llm.base import LLMError

                raise LLMError("budget_denied", "sem orçamento")
            return named
        return "Consigo ver ao vivo. De onde vocês saem?"

    llm = FakeLLMProvider(responder=respond)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_settings] = lambda: Settings(curiosity_enabled=False)
    run_genesis(db)
    db.commit()
    return llm


def _talk(client, headers, text, conversation=None):
    conversation = conversation or client.post("/conversations", headers=headers).json()["id"]
    sent = client.post(
        f"/conversations/{conversation}/messages", headers=headers, json={"content": text}
    )
    assert sent.status_code == 200, sent.text
    return conversation


def _run_title_jobs(db, llm):
    handle = title_handler(Settings(), llm)
    for job in db.query(ScheduledJob).filter_by(kind=title.JOB_KIND, status=queue.PENDING):
        handle(db, job)
        job.status = queue.DONE
    db.commit()


def test_the_first_exchange_gets_a_short_title_once(client, db):
    llm = _world(client, db)
    headers = _login(client, db)
    conversation = _talk(client, headers, "quanto custa viajar pro Chile em agosto?")
    assert client.get("/conversations", headers=headers).json()[0]["title"] is None
    _run_title_jobs(db, llm)
    listed = client.get("/conversations", headers=headers).json()
    assert listed[0]["title"] == "Viagem ao Chile em agosto"
    _talk(client, headers, "saindo de BH", conversation)
    _run_title_jobs(db, llm)
    asked = [p for p in llm.prompts if p[0].content == title.INSTRUCTIONS]
    assert len(asked) == 1
    usage = db.query(ModelUsage).filter_by(purpose=title.PURPOSE).one()
    assert usage.outcome == "success"


def test_without_budget_the_menu_keeps_the_date(client, db):
    llm = _world(client, db, fail=True)
    headers = _login(client, db)
    _talk(client, headers, "oi, tudo bem?")
    _run_title_jobs(db, llm)
    assert client.get("/conversations", headers=headers).json()[0]["title"] is None


def test_titles_are_cleaned_and_kept_short():
    assert title.clean('Título: "Bug no login do app."') == "Bug no login do app"
    assert title.clean("uma conversa sobre muitas coisas diferentes ao mesmo tempo") == (
        "Uma conversa sobre muitas coisas diferentes"
    )
    assert title.clean("Oi") is None
