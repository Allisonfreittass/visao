"""Phase 2 acceptance: end-to-end voice turn latency with the real components.

Server-side path for each turn, all real: spoken question (WAV) -> faster-whisper -> LLM reply
(configured provider, fresh conversation, in-memory DB) -> first sentence synthesized by the
agent's voice. The browser adds the VAD silence hangover (fixed, not measured here) and network
time on top; both are reported separately.

    .venv/bin/python -m experiments.voice_latency
"""

import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.llm import build_llm_provider, missing_llm_settings
from apps.api.settings import get_settings
from core.conversation.service import Budgets, reply
from core.identity.genesis import run_genesis
from infrastructure.database.base import Base
from infrastructure.database.models import Conversation, User
from integrations.stt.engine import load_stt
from integrations.tts.catalog import load_provider
from integrations.tts.text import sentences

RESULTS_DIR = Path(__file__).parent / "results"
VAD_HANGOVER_MS = 800  # apps/web/src/voice/vad.ts DEFAULT_VAD.hangoverMs

QUESTIONS = [
    "Oi, tudo bem? Em uma frase, o que você consegue fazer?",
    "Qual é a capital do Japão?",
    "Me dá uma dica rápida para dormir melhor.",
]


def main() -> int:
    settings = get_settings()
    provider = build_llm_provider(settings)
    if provider is None:
        print("LLM não configurado. Faltam: " + ", ".join(missing_llm_settings(settings)))
        return 1
    if not settings.stt_model:
        print("VISION_STT_MODEL vazio.")
        return 1
    voice_id = (settings.tts_approved_voices.split(",") or [""])[0].strip()
    if not voice_id:
        print("VISION_TTS_APPROVED_VOICES vazio.")
        return 1

    print("Carregando modelos (fora da medição)...", flush=True)
    stt = load_stt(settings.stt_model, settings.stt_models_dir)
    tts = load_provider(voice_id, settings.tts_models_dir)
    tts.synthesize("Aquecendo os modelos.")
    stt.transcribe(tts.synthesize("Aquecendo.").to_wav())

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    budgets = Budgets(settings.llm_daily_budget_usd, settings.llm_conversation_budget_usd)

    turns = []
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        identity = run_genesis(session).identity
        user = User(email="latencia@bench.local", password_hash="!")  # noqa: S106 (never logs in)
        session.add(user)
        session.commit()

        for question in QUESTIONS:
            spoken = tts.synthesize(question).to_wav()  # the "user" speaking, not timed

            started = time.perf_counter()
            transcript = stt.transcribe(spoken)
            after_stt = time.perf_counter()

            conversation = Conversation(user_id=user.id, identity_id=identity.id)
            session.add(conversation)
            session.commit()
            turn = reply(
                session,
                conversation=conversation,
                identity=identity,
                owner=user,
                user_text=transcript.text,
                provider=provider,
                budgets=budgets,
                max_output_tokens=settings.llm_max_output_tokens,
                context_char_budget=settings.llm_context_char_budget,
            )
            after_llm = time.perf_counter()

            first_sentence = sentences(turn.assistant_message.content)[0]
            tts.synthesize(first_sentence)
            after_tts = time.perf_counter()

            row = {
                "question": question,
                "transcript": transcript.text,
                "reply": turn.assistant_message.content,
                "served_by": f"{turn.usage.provider}:{turn.usage.model}",
                "stt_ms": round((after_stt - started) * 1000),
                "llm_ms": round((after_llm - after_stt) * 1000),
                "tts_first_sentence_ms": round((after_tts - after_llm) * 1000),
                "server_total_ms": round((after_tts - started) * 1000),
            }
            row["perceived_ms"] = row["server_total_ms"] + VAD_HANGOVER_MS
            turns.append(row)
            print(
                f"- {question}\n  ouvido: {transcript.text}\n  STT {row['stt_ms']} ms | LLM "
                f"{row['llm_ms']} ms | TTS 1ª frase {row['tts_first_sentence_ms']} ms | "
                f"servidor {row['server_total_ms']} ms | percebido ~{row['perceived_ms']} ms",
                flush=True,
            )

    def median(key: str) -> int:
        return round(statistics.median(t[key] for t in turns))

    summary = {
        k: median(k)
        for k in ("stt_ms", "llm_ms", "tts_first_sentence_ms", "server_total_ms", "perceived_ms")
    }
    print(f"\nMedianas: {summary}")
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"voice-latency-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(
        json.dumps(
            {
                "ran_at": datetime.now(UTC).isoformat(),
                "stt_model": settings.stt_model,
                "voice": voice_id,
                "llm": f"{provider.name}:{provider.model}",
                "vad_hangover_ms": VAD_HANGOVER_MS,
                "medians": summary,
                "turns": turns,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"Resultado salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
