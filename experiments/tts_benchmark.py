"""Phase 2b: Kokoro vs Piper in pt-BR, on this machine's CPU.

Each configuration runs in its own subprocess so peak memory is not shared between them.
Audio samples are written to experiments/results/tts/<config>/ for listening (not versioned).

    .venv/bin/python -m experiments.tts_benchmark
    .venv/bin/python -m experiments.tts_benchmark --configs kokoro-int8-dora,piper-faber

Metrics per configuration:
  load_s            model load time
  cold_s            first synthesis after load (includes ONNX warm-up)
  rtf               synthesis time / audio duration, warm (lower is better; < 1 is real time)
  first_audio_s     time to the first sentence of the long reply when synthesized sentence by
                    sentence (what a listener waits before hearing anything)
  peak_rss_mb       peak resident memory of the process
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

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "tts"
OUT_DIR = Path(__file__).parent / "results" / "tts"
RESULTS_DIR = Path(__file__).parent / "results"

# The int8 Kokoro model was dropped: it outputs NaN audio for very short inputs ("Oi.",
# "Sim.") with every pt-BR voice (research log 2026-10-31-fase-2b-tts.md).
CONFIGS = {
    "kokoro-dora": ("kokoro", "kokoro-v1.0.onnx", "pf_dora"),
    "kokoro-alex": ("kokoro", "kokoro-v1.0.onnx", "pm_alex"),
    "kokoro-santa": ("kokoro", "kokoro-v1.0.onnx", "pm_santa"),
    "piper-faber": ("piper", "pt_BR-faber-medium.onnx", None),
    "piper-cadu": ("piper", "pt_BR-cadu-medium.onnx", None),
}

SAMPLES = {
    "minima": "Sim.",
    "curta": "Olá! Tudo bem com você?",
    "media": (
        "Você escolheu o pgloader para migrar o banco de MySQL para PostgreSQL, e vai testar "
        "primeiro num ambiente de homologação."
    ),
    "numeros": (
        "A reunião ficou para o dia 3 de abril de 2027, às 14h30. O orçamento é de R$ 1.250,50 "
        "e a API responde em 120 ms."
    ),
    "longa": (
        "Não tenho lembranças de conversas anteriores, exceto os itens que foram curados e "
        "guardados com o seu consentimento. Neste momento, sei que você prefere respostas "
        "curtas e diretas. Se quiser, posso apagar essas memórias a qualquer momento. "
        "Também posso explicar como a curadoria decide o que guardar."
    ),
}


def _build(engine: str, model_file: str, voice: str | None):
    from integrations.tts.engines import KokoroTTS, PiperTTS

    if engine == "kokoro":
        return KokoroTTS(
            MODELS / "kokoro" / model_file, MODELS / "kokoro" / "voices-v1.0.bin", voice
        )
    return PiperTTS(MODELS / "piper" / model_file)


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux kilobytes.
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


def run_one(name: str) -> dict:
    from integrations.tts.text import sentences

    engine, model_file, voice = CONFIGS[name]
    out = OUT_DIR / name
    out.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    tts = _build(engine, model_file, voice)
    load_s = time.perf_counter() - started

    started = time.perf_counter()
    tts.synthesize("Aquecendo.")
    cold_s = time.perf_counter() - started

    synth_total = audio_total = 0.0
    per_sample = {}
    for key, text in SAMPLES.items():
        started = time.perf_counter()
        audio = tts.synthesize(text)
        elapsed = time.perf_counter() - started
        (out / f"{key}.wav").write_bytes(audio.to_wav())
        synth_total += elapsed
        audio_total += audio.duration_seconds
        per_sample[key] = {
            "synth_s": round(elapsed, 3),
            "audio_s": round(audio.duration_seconds, 3),
        }

    first = sentences(SAMPLES["longa"])[0]
    started = time.perf_counter()
    tts.synthesize(first)
    first_audio_s = time.perf_counter() - started

    return {
        "config": name,
        "engine": engine,
        "model": model_file,
        "voice": tts.voice,
        "load_s": round(load_s, 3),
        "cold_s": round(cold_s, 3),
        "rtf": round(synth_total / audio_total, 3),
        "first_audio_s": round(first_audio_s, 3),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "samples": per_sample,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", default=",".join(CONFIGS))
    parser.add_argument("--one", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.one:
        print(json.dumps(run_one(args.one)))
        return 0

    results = []
    for name in [c for c in args.configs.split(",") if c in CONFIGS]:
        print(f"-> {name}", flush=True)
        proc = subprocess.run(  # noqa: S603 (fixed interpreter and our own module)
            [sys.executable, "-m", "experiments.tts_benchmark", "--one", name],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"   falhou: {proc.stderr.strip()[-400:]}")
            results.append({"config": name, "error": proc.stderr.strip()[-1000:]})
            continue
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        results.append(result)
        print(
            f"   carga {result['load_s']}s | 1ª síntese {result['cold_s']}s | RTF {result['rtf']} "
            f"| 1º áudio {result['first_audio_s']}s | pico {result['peak_rss_mb']} MB",
            flush=True,
        )

    run = {
        "ran_at": datetime.now(UTC).isoformat(),
        "machine": f"{platform.machine()} {platform.platform()}",
        "results": results,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"tts-benchmark-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2))
    print(f"\nResultado salvo em {path}\nAmostras de áudio em {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
