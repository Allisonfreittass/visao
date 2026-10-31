from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from apps.api.deps import AppSettings, CurrentUser, DbSession
from core.identity.genesis import get_identity
from core.identity.voice import resolve_voice, voice_history
from integrations.tts.base import TTSError, TTSProvider
from integrations.tts.catalog import approved_voices, load_provider
from integrations.tts.text import sentences

router = APIRouter(prefix="/voice", tags=["voice"])

TTSLoader = Callable[[str, str], TTSProvider]


def get_tts_loader() -> TTSLoader:
    """Override point for tests; the real loader keeps engines in memory."""
    return load_provider


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
            status.HTTP_422_UNPROCESSABLE_ENTITY,
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
