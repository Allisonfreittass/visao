"""Phase 2c: faster-whisper tiny/base/small in pt-BR on this machine's CPU.

Test speech is synthesized with the approved voice (Kokoro dora) from fixed texts, clean and with
white noise at ~15 dB SNR. Synthetic speech is cleaner than a real microphone, so these word
error rates are optimistic; they rank models, they do not predict field accuracy.

    .venv/bin/python -m experiments.stt_benchmark
"""

import argparse
import json
import platform
import resource
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODELS_STT = str(ROOT / "models" / "stt")
AUDIO_DIR = Path(__file__).parent / "results" / "stt-audio"
RESULTS_DIR = Path(__file__).parent / "results"
SIZES = ["tiny", "base", "small"]
SNR_DB = 15.0

UTTERANCES = [
    "Qual ferramenta eu escolhi para a migração do banco de dados?",
    "Me lembra de revisar o orçamento amanhã às três da tarde.",
    "Você consegue explicar a diferença entre memória episódica e memória semântica?",
    "Pare de falar, por favor.",
    "Eu prefiro respostas curtas e diretas.",
    "O projeto usa PostgreSQL e FastAPI no servidor.",
]


# "às 3 da tarde" and "às três da tarde" are the same transcription; count them as equal.
_NUMBER_WORDS = {
    "0": "zero",
    "1": "um",
    "2": "dois",
    "3": "tres",
    "4": "quatro",
    "5": "cinco",
    "6": "seis",
    "7": "sete",
    "8": "oito",
    "9": "nove",
    "10": "dez",
}


def words(text: str) -> list[str]:
    from core.memory.text import fold

    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in fold(text))
    return [_NUMBER_WORDS.get(w, w) for w in cleaned.split()]


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = words(reference), words(hypothesis)
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        previous, row[0] = row[0], i
        for j, h in enumerate(hyp, start=1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (r != h))
    return row[-1] / max(len(ref), 1)


def generate_audio() -> None:
    """Writes clean and noisy WAVs once; reused by every model run."""
    from integrations.tts.base import SynthesizedAudio
    from integrations.tts.catalog import load_provider

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    if len(list(AUDIO_DIR.glob("*.wav"))) == 2 * len(UTTERANCES):
        return
    tts = load_provider("kokoro-dora", str(ROOT / "models" / "tts"))
    rng = np.random.default_rng(42)
    for i, text in enumerate(UTTERANCES):
        audio = tts.synthesize(text)
        (AUDIO_DIR / f"{i}-clean.wav").write_bytes(audio.to_wav())
        signal = np.frombuffer(audio.pcm16, dtype="<i2").astype(np.float32)
        noise_power = np.mean(signal**2) / (10 ** (SNR_DB / 10))
        noisy = signal + rng.normal(0, np.sqrt(noise_power), signal.shape)
        pcm = np.clip(noisy, -32768, 32767).astype("<i2").tobytes()
        (AUDIO_DIR / f"{i}-noisy.wav").write_bytes(
            SynthesizedAudio(pcm, audio.sample_rate).to_wav()
        )


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


def run_one(size: str) -> dict:
    from integrations.stt.engine import WhisperSTT

    started = time.perf_counter()
    stt = WhisperSTT(size, MODELS_STT)
    load_s = time.perf_counter() - started
    stt.transcribe((AUDIO_DIR / "0-clean.wav").read_bytes())  # warm-up

    rows = []
    for condition in ("clean", "noisy"):
        for i, reference in enumerate(UTTERANCES):
            result = stt.transcribe((AUDIO_DIR / f"{i}-{condition}.wav").read_bytes())
            rows.append(
                {
                    "condition": condition,
                    "reference": reference,
                    "hypothesis": result.text,
                    "wer": round(wer(reference, result.text), 3),
                    "elapsed_s": round(result.elapsed_seconds, 3),
                    "audio_s": round(result.audio_seconds, 3),
                }
            )

    def mean(key: str, condition: str) -> float:
        values = [r[key] for r in rows if r["condition"] == condition]
        return round(sum(values) / len(values), 3)

    return {
        "model": size,
        "load_s": round(load_s, 2),
        "wer_clean": mean("wer", "clean"),
        "wer_noisy": mean("wer", "noisy"),
        "mean_latency_s": mean("elapsed_s", "clean"),
        "rtf": round(sum(r["elapsed_s"] for r in rows) / sum(r["audio_s"] for r in rows), 3),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--one", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.one:
        print(json.dumps(run_one(args.one), ensure_ascii=False))
        return 0

    generate_audio()
    results = []
    for size in SIZES:
        print(f"-> {size}", flush=True)
        proc = subprocess.run(  # noqa: S603 (fixed interpreter and our own module)
            [sys.executable, "-m", "experiments.stt_benchmark", "--one", size],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"   falhou: {proc.stderr.strip()[-400:]}")
            continue
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        results.append(result)
        print(
            f"   WER limpo {result['wer_clean']:.1%} | com ruído {result['wer_noisy']:.1%} | "
            f"latência média {result['mean_latency_s']}s | RTF {result['rtf']} | "
            f"pico {result['peak_rss_mb']} MB",
            flush=True,
        )

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"stt-benchmark-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    path.write_text(
        json.dumps(
            {
                "ran_at": datetime.now(UTC).isoformat(),
                "machine": f"{platform.machine()} {platform.platform()}",
                "snr_db": SNR_DB,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"\nResultado salvo em {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
