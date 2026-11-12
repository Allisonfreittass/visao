"""Web Push: an opening reaches a closed app, only through the rules that already gate openings."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from apps.api.settings import Settings, get_settings
from core.initiatives import push
from core.mind import initiative
from infrastructure.database.models import PushSubscription
from integrations.push.webpush import PushResult, allowed_endpoint, generate_vapid_keys
from tests.integration.test_mind import NOON, _owner_client, setup, think

FCM = "https://fcm.googleapis.com/fcm/send/abc123"
KEYS = {"p256dh": "B" * 87, "auth": "a" * 22}


class RecordingSender:
    def __init__(self, result=None):
        self.sent = []
        self.result = result or PushResult(True)

    def send(self, subscription, payload):
        self.sent.append((subscription.endpoint, payload))
        return self.result


@pytest.fixture
def sender():
    recording = RecordingSender()
    push.configure(recording)
    yield recording
    push.configure(None)


def _subscribe(db, owner, endpoint=FCM):
    db.add(PushSubscription(owner_user_id=owner.id, endpoint=endpoint, p256dh="k", auth="a"))
    db.commit()


def test_an_opening_is_pushed_with_a_link_back_to_its_conversation(db, sender):
    owner = setup(db)
    _subscribe(db, owner)
    report = think(db, owner)
    assert report.delivery == "sent"
    [(endpoint, payload)] = sender.sent
    assert endpoint == FCM
    assert payload["url"].startswith("/?c=")
    assert payload["body"].startswith("Li o que escrevi ontem")
    assert len(payload["body"]) <= push.BODY_CHARS


def test_no_push_when_the_opening_itself_is_held_back(db, sender):
    owner = setup(db)
    _subscribe(db, owner)
    active = NOON - timedelta(hours=2) + timedelta(minutes=5)
    assert initiative.post(db, owner, "oi", active, 6).sent is False
    assert sender.sent == []


def test_a_gone_browser_is_forgotten_and_a_failing_one_dropped_after_a_few_tries(db):
    owner = setup(db)
    _subscribe(db, owner)
    push.configure(RecordingSender(PushResult(False, gone=True, detail="http_410")))
    try:
        assert push.send_to_owner(db, owner.id, title="t", body="b") == 0
        assert db.scalar(select(func.count()).select_from(PushSubscription)) == 0

        _subscribe(db, owner)
        push.configure(RecordingSender(PushResult(False, detail="ConnectTimeout")))
        for _ in range(push.MAX_FAILURES):
            push.send_to_owner(db, owner.id, title="t", body="b")
        assert db.scalar(select(func.count()).select_from(PushSubscription)) == 0
    finally:
        push.configure(None)


def test_push_is_off_until_configured(db):
    owner = setup(db)
    _subscribe(db, owner)
    assert push.send_to_owner(db, owner.id, title="t", body="b") == 0


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        (FCM, True),
        ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
        ("https://web.push.apple.com/QW", True),
        ("http://fcm.googleapis.com/x", False),
        ("https://evil.example/fcm.googleapis.com", False),
        ("https://fcm.googleapis.com.evil.example/x", False),
        ("https://127.0.0.1/x", False),
    ],
)
def test_only_known_push_services_are_ever_contacted(url, ok):
    assert allowed_endpoint(url) is ok


def test_vapid_keys_have_the_shapes_browsers_and_senders_expect():
    import base64

    public, private = generate_vapid_keys()
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    assert len(base64.urlsafe_b64decode(pad(public))) == 65
    assert len(base64.urlsafe_b64decode(pad(private))) == 32


def _push_settings():
    public, private = generate_vapid_keys()
    return Settings(
        webpush_public_key=public,
        webpush_private_key=private,
        webpush_subject="https://visao.example",
    )


def test_subscribe_test_and_unsubscribe_through_the_api(client, db, sender):
    owner, headers = _owner_client(client, db)
    assert client.get("/push", headers=headers).json()["enabled"] is False
    assert (
        client.post(
            "/push/subscriptions", json={"endpoint": FCM, "keys": KEYS}, headers=headers
        ).status_code
        == 503
    )

    settings = _push_settings()
    client.app.dependency_overrides[get_settings] = lambda: settings
    state = client.get("/push", headers=headers).json()
    assert state["enabled"] is True and state["public_key"] == settings.webpush_public_key

    bad = {"endpoint": "https://example.com/hook", "keys": KEYS}
    assert client.post("/push/subscriptions", json=bad, headers=headers).status_code == 422
    for _ in range(2):  # idempotent per browser
        response = client.post(
            "/push/subscriptions", json={"endpoint": FCM, "keys": KEYS}, headers=headers
        )
        assert response.status_code == 204
    assert client.get("/push", headers=headers).json()["subscriptions"] == 1

    assert client.post("/push/test", headers=headers).json() == {"sent": 1}
    assert sender.sent[0][1]["tag"] == "visao-test"

    response = client.request(
        "DELETE", "/push/subscriptions", json={"endpoint": FCM}, headers=headers
    )
    assert response.status_code == 204
    assert client.get("/push", headers=headers).json()["subscriptions"] == 0
    assert owner.id is not None


def test_push_routes_require_login(client):
    assert client.get("/push").status_code == 401
    assert client.post("/push/test").status_code == 401
