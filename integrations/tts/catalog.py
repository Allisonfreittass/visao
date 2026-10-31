"""Voices that exist on this installation, with the facts the agent can reason about.

Latency/memory figures come from experiments/tts_benchmark.py on the development Mac M1
(2026-10-31); they are measurements, not marketing. Which of these voices may be used at all is
decided by a human quality check (VISION_TTS_APPROVED_VOICES); which one is the agent's own is
decided by the agent (core/identity/voice.py).
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from integrations.tts.base import TTSProvider


@dataclass(frozen=True)
class VoiceSpec:
    id: str
    engine: str
    model_file: str
    engine_voice: str | None
    timbre: str
    first_audio_s: float
    peak_memory_mb: int
    license_note: str


CATALOG: dict[str, VoiceSpec] = {
    spec.id: spec
    for spec in [
        VoiceSpec(
            "kokoro-dora",
            "kokoro",
            "kokoro-v1.0.onnx",
            "pf_dora",
            "feminina",
            2.09,
            866,
            "pesos Apache-2.0, runtime MIT",
        ),
        VoiceSpec(
            "kokoro-alex",
            "kokoro",
            "kokoro-v1.0.onnx",
            "pm_alex",
            "masculina",
            2.21,
            895,
            "pesos Apache-2.0, runtime MIT",
        ),
        VoiceSpec(
            "kokoro-santa",
            "kokoro",
            "kokoro-v1.0.onnx",
            "pm_santa",
            "masculina",
            2.44,
            896,
            "pesos Apache-2.0, runtime MIT",
        ),
        VoiceSpec(
            "piper-faber",
            "piper",
            "pt_BR-faber-medium.onnx",
            None,
            "masculina",
            0.24,
            360,
            "runtime GPL-3.0; voz derivada de conjunto com restrições",
        ),
        VoiceSpec(
            "piper-cadu",
            "piper",
            "pt_BR-cadu-medium.onnx",
            None,
            "masculina",
            0.28,
            339,
            "runtime GPL-3.0; voz derivada de conjunto com restrições",
        ),
    ]
}


def approved_voices(setting: str) -> list[VoiceSpec]:
    """Parses VISION_TTS_APPROVED_VOICES, keeping catalog order and ignoring unknown ids."""
    wanted = {v.strip() for v in setting.split(",") if v.strip()}
    return [spec for spec in CATALOG.values() if spec.id in wanted]


def system_default(approved: list[VoiceSpec]) -> VoiceSpec | None:
    """Objective fallback until the agent decides: the approved voice with the lowest measured
    time to first audio. Not a taste judgment by anyone."""
    return min(approved, key=lambda s: s.first_audio_s, default=None)


@lru_cache(maxsize=2)
def load_provider(voice_id: str, models_dir: str) -> TTSProvider:
    """Loads (and keeps) the engine for one voice. Heavy: Kokoro takes ~0.9 GB of RAM."""
    from integrations.tts.engines import KokoroTTS, PiperTTS

    spec = CATALOG[voice_id]
    root = Path(models_dir)
    if spec.engine == "kokoro":
        return KokoroTTS(
            root / "kokoro" / spec.model_file,
            root / "kokoro" / "voices-v1.0.bin",
            voice=spec.engine_voice or "",
        )
    return PiperTTS(root / "piper" / spec.model_file)
