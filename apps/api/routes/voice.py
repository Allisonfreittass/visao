from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from apps.api.deps import AppSettings, CurrentUser, DbSession
from core.identity.genesis import get_identity
from core.identity.voice import resolve_voice, voice_history
from integrations.stt.engine import STTError, STTProvider, load_stt
from integrations.tts.base import TTSError, TTSProvider
from integrations.tts.catalog import approved_voices, load_provider
from integrations.tts.text import sentences

router = APIRouter(prefix="/voice", tags=["voice"])

TTSLoader = Callable[[str, str], TTSProvider]
STTLoader = Callable[[str, str], STTProvider]

ACCEPTED_AUDIO = ("audio/wav", "audio/x-wav", "audio/wave", "audio/webm", "audio/ogg", "audio/mp4")


def get_tts_loader() -> TTSLoader:
    """Override point for tests; the real loader keeps engines in memory."""
    return load_provider


def get_stt_loader() -> STTLoader:
    """Override point for tests; the real loader keeps the model in memory."""
    return load_stt


class TranscriptOut(BaseModel):
    text: str
    model: str
    audio_seconds: float
    elapsed_ms: int


class VoiceOption(BaseModel):
    id: str
    engine: str
    timbre: str
    first_audio_s: float


class VoiceEventOut(BaseModel):
    event_type: str
    previous_voice: str | None
    new_voice: str | None
    rationale_summary: str
    model_version: str
    created_at: datetime


class VoiceStatus(BaseModel):
    enabled: bool
    # Speech recognition available (VISION_STT_MODEL set).
    listening: bool
    approved: list[VoiceOption]
    current_voice: str | None
    # "chosen" = the agent's own decision; "system_default" = objective fallback, not a choice.
    source: str
    history: list[VoiceEventOut]


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


@router.get("/status")
def voice_status(db: DbSession, _user: CurrentUser, settings: AppSettings) -> VoiceStatus:
    approved = approved_voices(settings.tts_approved_voices)
    identity = get_identity(db)
    if identity is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Genesis ainda não foi executado")
    resolved = resolve_voice(identity, approved)
    return VoiceStatus(
        enabled=resolved.spec is not None,
        listening=bool(settings.stt_model),
        approved=[
            VoiceOption(id=s.id, engine=s.engine, timbre=s.timbre, first_audio_s=s.first_audio_s)
            for s in approved
        ],
        current_voice=resolved.spec.id if resolved.spec else None,
        source=resolved.source,
        history=[
            VoiceEventOut(
                event_type=e.event_type,
                previous_voice=e.previous_voice,
                new_voice=e.new_voice,
                rationale_summary=e.rationale_summary,
                model_version=e.model_version,
                created_at=e.created_at,
            )
            for e in voice_history(db, identity)
        ],
    )


@router.post("/sentences")
def split_sentences(body: TextIn, _user: CurrentUser) -> dict[str, list[str]]:
    """Speakable sentences of a reply, so the client can play the first while the rest is
    synthesized."""
    return {"sentences": sentences(body.text)}


@router.post("/tts", response_class=Response)
def synthesize(
    body: TextIn,
    db: DbSession,
    _user: CurrentUser,
    settings: AppSettings,
    loader: Annotated[TTSLoader, Depends(get_tts_loader)],
) -> Response:
    if len(body.text) > settings.tts_max_chars:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Texto longo demais para uma síntese (máx. {settings.tts_max_chars}); "
            "use /voice/sentences",
        )
    identity = get_identity(db)
    if identity is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Genesis ainda não foi executado")
    resolved = resolve_voice(identity, approved_voices(settings.tts_approved_voices))
    if resolved.spec is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Voz desativada: nenhuma voz aprovada (VISION_TTS_APPROVED_VOICES)",
        )
    try:
        audio = loader(resolved.spec.id, settings.tts_models_dir).synthesize(body.text)
    except (TTSError, OSError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Falha na síntese: {exc}") from exc
    return Response(
        content=audio.to_wav(),
        media_type="audio/wav",
        headers={"X-Voice-Id": resolved.spec.id, "X-Voice-Source": resolved.source},
    )


@router.post("/stt")
async def transcribe(
    request: Request,
    _user: CurrentUser,
    settings: AppSettings,
    loader: Annotated[STTLoader, Depends(get_stt_loader)],
) -> TranscriptOut:
    """One user turn of audio in, text out. The audio is not stored."""
    if not settings.stt_model:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Escuta desativada (VISION_STT_MODEL vazio)"
        )
    content_type = request.headers.get("content-type", "").split(";")[0].strip()
    if content_type not in ACCEPTED_AUDIO:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Envie áudio (WAV ou WebM)")
    too_large = HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Áudio longo demais")
    declared = request.headers.get("content-length")
    # Refuse oversized uploads before reading them into memory.
    if declared and declared.isdigit() and int(declared) > settings.stt_max_bytes:
        raise too_large
    # Chunked uploads carry no length: stop reading as soon as the cap is passed.
    buffer = bytearray()
    async for chunk in request.stream():
        buffer.extend(chunk)
        if len(buffer) > settings.stt_max_bytes:
            raise too_large
    audio = bytes(buffer)
    if not audio:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Áudio vazio")
    try:
        engine = loader(settings.stt_model, settings.stt_models_dir)
        # CPU-bound (~0.3-1 s): off the event loop so other requests keep flowing.
        result = await run_in_threadpool(engine.transcribe, audio)
    except (STTError, OSError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Falha na transcrição: {exc}") from exc
    return TranscriptOut(
        text=result.text,
        model=engine.model,
        audio_seconds=round(result.audio_seconds, 3),
        elapsed_ms=round(result.elapsed_seconds * 1000),
    )
