"""Speech synthesis interface. Engines are self-hosted with open weights (docs/VOICE.md)."""

import io
import wave
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SynthesizedAudio:
    pcm16: bytes  # mono, little-endian signed 16-bit
    sample_rate: int

    @property
    def duration_seconds(self) -> float:
        return len(self.pcm16) / 2 / self.sample_rate

    def to_wav(self) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(self.pcm16)
        return buffer.getvalue()


class TTSError(Exception):
    pass


class TTSProvider(Protocol):
    engine: str
    voice: str

    def synthesize(self, text: str) -> SynthesizedAudio: ...
