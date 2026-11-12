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


@dataclass
class FakeSTT:
    model: str = "faster-whisper-fake"
    reply: str = "olá, tudo bem?"
    fail: bool = False
    received: list[bytes] = field(default_factory=list)

    def transcribe(self, audio: bytes):
        from integrations.stt.engine import STTError, Transcript

        self.received.append(audio)
        if self.fail:
            raise STTError("áudio ilegível")
        return Transcript(self.reply, "pt", 1.5, 0.2)


@pytest.fixture
def stt(client: TestClient) -> Iterator[FakeSTT]:
    from apps.api.routes.voice import get_stt_loader

    engine = FakeSTT()
    client.app.dependency_overrides[get_stt_loader] = lambda: lambda _size, _dir: engine
    yield engine


def _enable_stt(client: TestClient, **extra: object) -> None:
    client.app.dependency_overrides[get_settings] = lambda: Settings(stt_model="base", **extra)


def test_stt_transcribes_audio(client: TestClient, db: Session, stt: FakeSTT) -> None:
    headers = {**_login(client, db), "Content-Type": "audio/wav"}
    _enable_stt(client)

    response = client.post("/voice/stt", headers=headers, content=b"RIFF....fake")

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "olá, tudo bem?"
    assert body["elapsed_ms"] == 200
    assert stt.received == [b"RIFF....fake"]


def test_stt_disabled_by_default(client: TestClient, db: Session, stt: FakeSTT) -> None:
    headers = {**_login(client, db), "Content-Type": "audio/wav"}
    client.app.dependency_overrides[get_settings] = lambda: Settings(stt_model="")
    assert client.post("/voice/stt", headers=headers, content=b"x").status_code == 503
    assert stt.received == []


@pytest.mark.parametrize(
    ("content_type", "body", "expected"),
    [
        ("application/json", b"{}", 415),
        ("audio/wav", b"", 422),
        ("audio/wav", b"x" * 20_001, 413),
    ],
)
def test_stt_rejects_bad_uploads(
    client: TestClient, db: Session, stt: FakeSTT, content_type: str, body: bytes, expected: int
) -> None:
    headers = {**_login(client, db), "Content-Type": content_type}
    _enable_stt(client, stt_max_bytes=20_000)
    assert client.post("/voice/stt", headers=headers, content=body).status_code == expected
    assert stt.received == []


def test_stt_failure_is_reported(client: TestClient, db: Session, stt: FakeSTT) -> None:
    headers = {**_login(client, db), "Content-Type": "audio/webm"}
    _enable_stt(client)
    stt.fail = True
    assert client.post("/voice/stt", headers=headers, content=b"webm").status_code == 502


def test_status_reports_listening(client: TestClient, db: Session, loaded) -> None:
    run_genesis(db)
    headers = _login(client, db)
    _enable_stt(client)
    assert client.get("/voice/status", headers=headers).json()["listening"] is True


def test_stt_caps_chunked_uploads_without_content_length(
    client: TestClient, db: Session, stt: FakeSTT
) -> None:
    headers = {**_login(client, db), "Content-Type": "audio/wav"}
    _enable_stt(client, stt_max_bytes=20_000)

    def chunks():
        # A generator body is sent chunked, with no Content-Length header.
        for _ in range(100):
            yield b"x" * 5_000

    response = client.post("/voice/stt", headers=headers, content=chunks())
    assert response.status_code == 413
    assert stt.received == []
    ok = client.post("/voice/stt", headers=headers, content=iter([b"RIFF", b"....fake"]))
    assert ok.status_code == 200 and stt.received == [b"RIFF....fake"]
