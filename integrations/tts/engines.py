"""Kokoro (Apache-2.0 weights, MIT runtime) and Piper (GPL-3.0 runtime) on ONNX Runtime, CPU.

The engine libraries are imported when a provider is built, so the API runs without the
optional `[tts]` extra installed.
"""

from pathlib import Path

import numpy as np

from integrations.tts.base import SynthesizedAudio, TTSError


def _float_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767).astype("<i2").tobytes()


class KokoroTTS:
    engine = "kokoro"

    def __init__(
        self,
        model_path: Path,
        voices_path: Path,
        voice: str = "pf_dora",
        lang: str = "pt-br",
        speed: float = 1.0,
    ) -> None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise TTSError("kokoro-onnx not installed (pip install -e '.[tts]')") from exc
        self._kokoro = Kokoro(str(model_path), str(voices_path))
        if voice not in self._kokoro.get_voices():
            raise TTSError(f"unknown Kokoro voice {voice!r}")
        self.voice = voice
        self._lang = lang
        self._speed = speed

    def synthesize(self, text: str) -> SynthesizedAudio:
        try:
            samples, sample_rate = self._kokoro.create(
                text, voice=self.voice, speed=self._speed, lang=self._lang
            )
        except ValueError as exc:
            # Raised by Kokoro's silence trimming when the model output is all NaN.
            raise TTSError(f"Kokoro produced no usable audio for {text!r}") from exc
        if samples.size == 0 or np.isnan(samples).any():
            # Seen with the int8 model on very short inputs ("Oi.", "Sim."): never play it.
            raise TTSError(f"Kokoro produced invalid audio (NaN) for {text!r}")
        return SynthesizedAudio(_float_to_pcm16(samples), sample_rate)


class PiperTTS:
    engine = "piper"

    def __init__(self, model_path: Path) -> None:
        try:
            from piper import PiperVoice
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise TTSError("piper-tts not installed (pip install -e '.[tts]')") from exc
        self._voice = PiperVoice.load(model_path)
        self.voice = Path(model_path).stem

    def synthesize(self, text: str) -> SynthesizedAudio:
        pcm = b"".join(chunk.audio_int16_bytes for chunk in self._voice.synthesize(text))
        return SynthesizedAudio(pcm, self._voice.config.sample_rate)
