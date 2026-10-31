from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.cli import create_user
from apps.api.routes.voice import get_tts_loader
from apps.api.settings import Settings, get_settings
from core.identity.genesis import run_genesis
from core.identity.voice import VoiceDecision, record_voice_decision
from integrations.tts.base import SynthesizedAudio, TTSError
from integrations.tts.catalog import CATALOG

PASSWORD = "senha-de-teste-longa"


@dataclass
class FakeTTS:
    voice: str
    engine: str = "fake"
    fail: bool = False
    texts: list[str] = field(default_factory=list)

    def synthesize(self, text: str) -> SynthesizedAudio:
        self.texts.append(text)
        if self.fail:
            raise TTSError("falha simulada")
        return SynthesizedAudio(b"\x01\x00" * 2400, 24000)


@pytest.fixture
def loaded(client: TestClient) -> Iterator[dict[str, FakeTTS]]:
    engines: dict[str, FakeTTS] = {}

    def loader(voice_id: str, _models_dir: str) -> FakeTTS:
        return engines.setdefault(voice_id, FakeTTS(voice=voice_id))

    client.app.dependency_overrides[get_tts_loader] = lambda: loader
    yield engines


def _approve(client: TestClient, voices: str) -> None:
    client.app.dependency_overrides[get_settings] = lambda: Settings(tts_approved_voices=voices)


def _login(client: TestClient, db: Session) -> dict[str, str]:
    create_user(db, "a@exemplo.com", PASSWORD)
    token = client.post(
        "/auth/login", data={"username": "a@exemplo.com", "password": PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_voice_disabled_without_approved_voices(client: TestClient, db: Session, loaded) -> None:
    run_genesis(db)
    headers = _login(client, db)
    _approve(client, "")

    assert client.get("/voice/status", headers=headers).json()["enabled"] is False
    response = client.post("/voice/tts", headers=headers, json={"text": "Oi."})
    assert response.status_code == 503
    assert loaded == {}


def test_default_voice_is_labelled_system_default(client: TestClient, db: Session, loaded):
    run_genesis(db)
    headers = _login(client, db)
    _approve(client, "kokoro-dora")

    body = client.get("/voice/status", headers=headers).json()
    assert (body["current_voice"], body["source"]) == ("kokoro-dora", "system_default")

    response = client.post("/voice/tts", headers=headers, json={"text": "Olá."})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content[:4] == b"RIFF"
    assert response.headers["X-Voice-Source"] == "system_default"
    assert loaded["kokoro-dora"].texts == ["Olá."]


def test_agents_choice_is_used_and_reported(client: TestClient, db: Session, loaded) -> None:
    identity = run_genesis(db).identity
    headers = _login(client, db)
    _approve(client, "kokoro-dora,piper-faber")
    record_voice_decision(
        db,
        identity,
        VoiceDecision("choose", "porque sim", "fake", "fake-1", voice_id="kokoro-dora"),
        [CATALOG["kokoro-dora"], CATALOG["piper-faber"]],
    )

    body = client.get("/voice/status", headers=headers).json()
    assert (body["current_voice"], body["source"]) == ("kokoro-dora", "chosen")
    assert [e["event_type"] for e in body["history"]] == ["CHOSEN"]
    response = client.post("/voice/tts", headers=headers, json={"text": "Oi."})
    assert response.headers["X-Voice-Id"] == "kokoro-dora"


def test_synthesis_failure_is_reported_not_faked(client: TestClient, db: Session, loaded):
    run_genesis(db)
    headers = _login(client, db)
    _approve(client, "kokoro-dora")
    loaded["kokoro-dora"] = FakeTTS(voice="kokoro-dora", fail=True)

    response = client.post("/voice/tts", headers=headers, json={"text": "Oi."})
    assert response.status_code == 502


def test_long_text_must_be_split_first(client: TestClient, db: Session, loaded) -> None:
    run_genesis(db)
    headers = _login(client, db)
    _approve(client, "kokoro-dora")
    long_text = "Uma frase. " * 100

    assert client.post("/voice/tts", headers=headers, json={"text": long_text}).status_code == 422
    parts = client.post("/voice/sentences", headers=headers, json={"text": long_text}).json()
    assert len(parts["sentences"]) == 100


def test_voice_requires_login(client: TestClient) -> None:
    assert client.post("/voice/tts", json={"text": "Oi."}).status_code == 401
    assert client.get("/voice/status").status_code == 401
