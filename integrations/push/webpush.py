"""Web Push (RFC 8030) with VAPID (RFC 8292): the only way an opening reaches a closed app.

The payload is encrypted for the browser's own keys (aes128gcm), so the push service only routes
it. Endpoints are restricted to the known browser push services: the server never POSTs to an
address someone typed.
"""

import base64
import json
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# Chrome/Edge/Android (FCM), Firefox, Safari/iOS, Windows. Suffix match on the hostname.
PUSH_SERVICE_HOSTS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)
TIMEOUT_SECONDS = 5.0
TTL_SECONDS = 6 * 60 * 60  # an opening older than this is stale; the push service may drop it
# Everything sent is something the owner should see now. Without it, Apple and FCM may hold the
# message until the phone wakes on its own (battery saver, low power mode).
HEADERS = {"Urgency": "high"}


@dataclass(frozen=True)
class Subscription:
    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class PushResult:
    ok: bool
    gone: bool = False  # 404/410: the browser unsubscribed; drop the record
    detail: str = ""


class PushSender(Protocol):
    def send(self, subscription: Subscription, payload: dict[str, str]) -> PushResult: ...


def allowed_endpoint(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or len(endpoint) > 2048:
        return False
    return any(host == known or host.endswith("." + known) for known in PUSH_SERVICE_HOSTS)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_vapid_keys() -> tuple[str, str]:
    """(public, private) in the formats the browser and the sender expect: the public key is the
    65-byte uncompressed P-256 point (applicationServerKey), the private one the raw 32 bytes."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64url(public), _b64url(private)


class WebPushSender:
    def __init__(self, private_key: str, subject: str) -> None:
        self._private_key = private_key
        self._subject = subject

    def send(self, subscription: Subscription, payload: dict[str, str]) -> PushResult:
        from pywebpush import WebPushException, webpush

        if not allowed_endpoint(subscription.endpoint):
            return PushResult(False, gone=True, detail="endpoint_not_allowed")
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._subject},
                timeout=TIMEOUT_SECONDS,
                ttl=TTL_SECONDS,
                headers=dict(HEADERS),
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else 0
            return PushResult(False, gone=status in (404, 410), detail=f"http_{status}")
        except Exception as exc:  # network, bad key: never break the caller
            return PushResult(False, detail=type(exc).__name__)
        return PushResult(True)
