"""A link in the message is opened before the reply, shown to the model as data, stated as an
action actually taken, and listed with the reply's sources."""

import hashlib

from apps.api.links import get_link_reader
from apps.api.llm import get_llm_provider
from apps.api.settings import Settings, get_settings
from core.conversation.links import LinkRead
from core.identity.genesis import run_genesis
from infrastructure.database.models import ArmDevice, User
from tests.fakes import FakeLLMProvider
from tests.integration.test_curiosity_api import _login, _turn


class FakeLinks:
    def __init__(self, reads):
        self.reads, self.texts = reads, []

    def read(self, text):
        self.texts.append(text)
        return list(self.reads) if "https://" in text else []


def world(client, db, reads):
    llm = FakeLLMProvider(reply_text="Li o README: é um assistente.")
    links = FakeLinks(reads)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_link_reader] = lambda: links
    client.app.dependency_overrides[get_settings] = lambda: Settings()
    run_genesis(db)
    db.commit()
    return llm, links


REPO = LinkRead("https://github.com/dono/projeto", "github", "Repositório dono/projeto\nREADME: oi")


def test_a_sent_repository_is_read_and_listed_as_a_source(client, db):
    llm, links = world(client, db, [REPO])
    headers = _login(client, db)
    _, body = _turn(client, headers, "o que acha disso? https://github.com/dono/projeto")
    system = llm.prompts[-1][0].content
    assert '<link url="https://github.com/dono/projeto">' in system and "README: oi" in system
    assert "os links que a pessoa mandou foram abertos agora" in system
    assert "abrir os links que o interlocutor manda" in system
    assert {"title": "dono/projeto", "url": REPO.url, "source": "GitHub"} in body["sources"]


def test_a_link_that_did_not_open_is_said_and_not_claimed_as_read(client, db):
    broken = LinkRead("https://quebrado.com", "page", failure="a página não abriu")
    llm, _ = world(client, db, [broken])
    headers = _login(client, db)
    _, body = _turn(client, headers, "vê https://quebrado.com")
    system = llm.prompts[-1][0].content
    assert "Não consegui abrir: a página não abriu" in system
    assert "tentei abrir os links" in system and "foram abertos agora" not in system
    assert body["sources"] == []


def test_without_links_nothing_is_read_and_no_action_is_claimed(client, db):
    llm, links = world(client, db, [REPO])
    headers = _login(client, db)
    _turn(client, headers, "bom dia")
    assert "<link" not in llm.prompts[-1][0].content
    assert "nenhuma" in llm.prompts[-1][0].content.split("Ações executadas neste turno")[1][:40]


def test_with_a_paired_mac_it_knows_it_can_work_there_and_only_with_approval(client, db):
    llm, _ = world(client, db, [])
    headers = _login(client, db)
    owner = db.query(User).one()
    db.add(
        ArmDevice(
            owner_user_id=owner.id,
            name="Mac",
            token_hash=hashlib.sha256(b"t").hexdigest(),
            projects=["visao", "mercado"],
            version="1",
        )
    )
    db.commit()
    _turn(client, headers, "bom dia")
    system = llm.prompts[-1][0].content
    assert "Claude Code no Mac do interlocutor, só nos projetos mercado, visao" in system
    assert "arquivos fora dos projetos liberados no Mac" in system
