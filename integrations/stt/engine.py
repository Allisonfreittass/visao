"""Speech-to-text with faster-whisper (MIT, CTranslate2) on CPU.

The library is imported when the engine is built, so the API runs without the `[stt]` extra.
"""

import io
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    audio_seconds: float
    elapsed_seconds: float


class STTError(Exception):
    pass


class STTProvider(Protocol):
    model: str

    def transcribe(self, audio: bytes) -> Transcript: ...


class WhisperSTT:
    def __init__(
        self,
        size: str,
        models_dir: str,
        *,
        language: str = "pt",
        beam_size: int = 1,
        compute_type: str = "int8",
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise STTError("faster-whisper not installed (pip install -e '.[stt]')") from exc
        self.model = f"faster-whisper-{size}"
        self._language = language
        self._beam_size = beam_size
        self._whisper = WhisperModel(
            size, device="cpu", compute_type=compute_type, download_root=models_dir
        )

    def transcribe(self, audio: bytes) -> Transcript:
        """Accepts any container PyAV can decode (WAV, WebM/Opus, MP4/AAC...)."""
        started = time.perf_counter()
        try:
            segments, info = self._whisper.transcribe(
                io.BytesIO(audio),
                language=self._language,
                beam_size=self._beam_size,
                # Each turn is independent; carrying text over invites hallucinated repeats.
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:  # decoding errors come from several libraries
            raise STTError(f"could not transcribe audio: {type(exc).__name__}: {exc}") from exc
        return Transcript(
            text=text,
            language=info.language,
            audio_seconds=info.duration,
            elapsed_seconds=time.perf_counter() - started,
        )


@lru_cache(maxsize=1)
def load_stt(size: str, models_dir: str) -> STTProvider:
    return WhisperSTT(size, models_dir)
