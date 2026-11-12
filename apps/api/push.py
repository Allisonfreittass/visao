"""Builds the Web Push sender from settings; both the API and the worker call this at startup."""

from apps.api.settings import Settings
from core.initiatives import push
from integrations.push.webpush import PushSender, WebPushSender


def enabled(settings: Settings) -> bool:
    return bool(
        settings.webpush_public_key and settings.webpush_private_key and settings.webpush_subject
    )


def build_sender(settings: Settings) -> PushSender | None:
    if not enabled(settings):
        return None
    assert settings.webpush_private_key is not None and settings.webpush_subject is not None
    return WebPushSender(settings.webpush_private_key.get_secret_value(), settings.webpush_subject)


def configure_push(settings: Settings) -> None:
    push.configure(build_sender(settings))
