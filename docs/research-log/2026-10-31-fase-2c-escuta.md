# 2026-10-31: Fase 2c (escuta)

## STT: faster-whisper na CPU (Mac M1), `results/stt-benchmark-20261031T113731Z.json`

Áudio de teste: 6 frases em pt-BR sintetizadas pela voz `kokoro-dora`, limpas e com ruído branco a
~15 dB de SNR. **Voz sintética é mais limpa que microfone real**: os números ordenam modelos, não
preveem a precisão em uso. WER com algarismos 0–10 equivalentes ao número por extenso.

| Modelo | WER limpo | WER com ruído | Latência média | Pico de memória |
|---|---|---|---|---|
| tiny | 21,0% | 31,4% | 0,19 s | 380 MB |
| base | 6,2% | 16,5% | 0,35 s | 497 MB |
| small | 8,3% | 7,5% | 1,03 s | 957 MB |

Erros recorrentes: nomes técnicos ("PostgreSQL", "FastAPI" viraram "Postcreas SQL", "faz de API");
parte pode ser a pronúncia da própria voz sintética. "Pare de falar" com ruído falhou no base
("e espari de falar") e foi quase certo no small ("Espare de falar").

Incidente: `faster-whisper` 1.2.1 quebra com PyAV 19 (`av.open(metadata_errors=...)` removido);
fixado `av==16.1.0`.

## Latência ponta a ponta, `results/voice-latency-20261031T114218Z.json`

Componentes reais no Mac M1: pergunta falada (WAV) → STT base → LLM (Nemotron 3.5 Super pela API
da NVIDIA, reserva do OpenRouter sem cota) → 1ª frase da resposta em `kokoro-dora`.

| Pergunta | STT | LLM | TTS 1ª frase | Servidor | Percebido (+800 ms do VAD) |
|---|---|---|---|---|---|
| "Oi, tudo bem? Em uma frase, o que você consegue fazer?" | 381 ms | 2.734 ms | 196 ms | 3.311 ms | ~4,1 s |
| "Qual é a capital do Japão?" | 343 ms | 785 ms | 511 ms | 1.639 ms | ~2,4 s |
| "Me dá uma dica rápida para dormir melhor." | 375 ms | 3.500 ms | 1.484 ms | 5.359 ms | ~6,2 s |
| **Mediana** | **375 ms** | **2.734 ms** | **511 ms** | **3.311 ms** | **~4,1 s** |

Leitura: o LLM grátis (modelo de raciocínio, fila compartilhada) domina e varia muito. O TTS
cresce com o tamanho da primeira frase; quebrá-la na primeira vírgula reduziria o tempo até o
primeiro som. Não incluídos: rede, captura no navegador, decodificação no cliente.

## Verificado e não verificado

| Item | Estado |
|---|---|
| `/voice/stt` real com áudio de teste | 200; "pare de falar por favor." em 0,35 s (1,3 s na 1ª chamada, carga do modelo) |
| VAD, WAV, fila de fala | testes unitários (22 no frontend) |
| API de STT | testes com motor falso (tamanho, tipo, falha, desligado) |
| Botão "Conversa por voz" na interface | aparece com STT e voz ligados |
| **Conversa de vários turnos com microfone real** | **não verificado** pelo agente de programação (sem microfone no painel); depende do responsável |
| Barge-in com eco real de alto-falante | não verificado |
| iPhone | não verificado; exige HTTPS |
