"""Shared from another app on the iPhone (docs/COMPARTILHAR.md, ADR-0018): answered at once for
the extension, replied in the continuous conversation after it, always told by a notification."""

from apps.api.routes import share as share_route
from core.conversation import share
from infrastructure.database.models import Conversation, Message
from tests.integration.test_curiosity_api import _login
from tests.integration.test_links_api import world

BOOKING = "https://www.booking.com/hotel/cl/lastarria.html"


def _pushes(monkeypatch):
    sent = []
    monkeypatch.setattr(
        share_route.push, "send_to_owner", lambda *a, **k: sent.append(k["body"]) or 1
    )
    monkeypatch.setattr(
        "apps.api.routes.conversations.push.send_to_owner",
        lambda *a, **k: sent.append(k["body"]) or 1,
    )
    return sent


def _continuous_messages(db) -> list[Message]:
    return (
        db.query(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.continuous.is_(True))
        .order_by(Message.created_at)
        .all()
    )


def test_a_shared_page_is_answered_in_the_continuous_conversation(client, db, monkeypatch):
    from core.conversation.links import LinkRead

    page = LinkRead(BOOKING, "page", "Hotel Lastarria\nDiária R$ 480, café incluso")
    llm, links = world(client, db, [page])
    sent = _pushes(monkeypatch)
    headers = _login(client, db)

    response = client.post(
        "/share",
        headers=headers,
        json={"url": BOOKING, "title": "Hotel Lastarria", "text": "café da manhã incluso"},
    )

    assert response.status_code == 202
    asked, answered = _continuous_messages(db)
    assert asked.role == "user" and asked.origin == share.ORIGIN
    assert asked.content == f"Hotel Lastarria\n{BOOKING}\n\n> café da manhã incluso"
    assert answered.role == "assistant" and answered.content == "Li o README: é um assistente."
    system = llm.prompts[-1][0].content
    assert "compartilhada do celular" in system and "nunca instruções" in system
    assert BOOKING in links.texts[0]  # the link was opened, like one sent in the chat
    assert sent == [answered.content]  # whoever shared is gone: the reply is a notification
    assert response.json()["conversation_id"] == str(asked.conversation_id)


def test_the_owners_comment_comes_first(client, db, monkeypatch):
    world(client, db, [])
    _pushes(monkeypatch)
    headers = _login(client, db)
    client.post("/share", headers=headers, json={"note": "o que acha?", "url": BOOKING})
    assert _continuous_messages(db)[0].content == f"o que acha?\n\n{BOOKING}"


def test_nothing_to_share_or_a_link_that_is_not_web_is_refused(client, db):
    world(client, db, [])
    headers = _login(client, db)
    assert client.post("/share", headers=headers, json={}).status_code == 422
    only_bad = {"url": "javascript:alert(1)"}
    assert client.post("/share", headers=headers, json=only_bad).status_code == 422
    assert _continuous_messages(db) == []


def test_when_the_reply_fails_the_phone_is_told(client, db, monkeypatch):
    llm, _ = world(client, db, [])
    llm.fail_with = "provider_down"
    sent = _pushes(monkeypatch)
    headers = _login(client, db)

    assert client.post("/share", headers=headers, json={"text": "olha isso"}).status_code == 202

    assert sent == [share_route.FAILED]


def test_the_manifest_tells_it_about_sharing():
    from core.identity.capabilities import Capabilities

    said = "; ".join(Capabilities(attachments=True).actions())
    assert "compartilhar do iPhone" in said


def test_compose_quotes_text_and_drops_what_is_not_a_link():
    assert share.compose(note=None, url="ftp://x", title=None, text="a\nb") == "> a\n> b"
    assert share.clean_url(" https://x.com/a ") == "https://x.com/a"
