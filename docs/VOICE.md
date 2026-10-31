# Voz

> Estado: **Fase 2a concluída** (interface web com a bolha e os estados). Voz ainda não existe:
> **2b** (TTS) e **2c** (microfone, STT, barge-in) pendentes. Nenhuma latência foi medida.

## Restrições do master prompt

- Sem ElevenLabs, sem extrair modelos proprietários, sem copiar vozes sem autorização.
- `SpeechProvider`/`TTSService` próprios, com pesos abertos e licença adequada. "Serviço próprio
  com pesos abertos" não é "sintetizador treinado do zero"; o segundo fica para a Fase 7.
- Pipeline inicial: microfone → VAD → STT → núcleo/LLM → TTS → áudio.
- Streaming quando possível, barge-in, cancelamento, turn-taking, consentimento de microfone,
  fallback para texto, latência ponta a ponta medida.
- Nada de microfone ligado com o navegador fechado ou o app em segundo plano no iOS.
- Personalidade não muda o timbre.

## Interface (2a, feito)

- `apps/web`: React + TypeScript (Vite), mobile-first, tema escuro.
- **Bolha de partículas laranja** (`src/orb/`): ~940 partículas em duas camadas, rotação,
  respiração e turbulência por estado, transições suaves independentes de taxa de quadros,
  `prefers-reduced-motion` respeitado. Estados:

| Estado | Comportamento | Já usado? |
|---|---|---|
| `IDLE` | pulsação lenta | sim |
| `THINKING` | rotação rápida + turbulência | sim (aguardando resposta) |
| `DISCONNECTED` | cinza e parada | sim (`/health` falhou) |
| `LISTENING` | expande com o nível do microfone | só na demonstração (`?orb=demo`) |
| `SPEAKING` | expande com o nível do áudio gerado | só na demonstração |
| `INTERRUPTED` | contração rápida | só na demonstração |

- A interface não chama o agente de "VISÃO": mostra o nome escolhido ou "sem nome pessoal".

## Plano da 2b: TTS próprio

Candidatos (licenças a reconferir na fonte no dia da escolha, ver `MODEL_SELECTION.md`):

| Modelo | Licença (conhecimento prévio) | pt-BR | Hipótese a medir |
|---|---|---|---|
| Kokoro 82M | pesos Apache-2.0; fonemização via espeak-ng (GPL) | poucas vozes | qualidade boa, cabe em CPU |
| Piper | código GPL-3.0 (piper1-gpl); vozes com licenças próprias | várias vozes | muito leve e rápido, menos natural |

Medição prevista (no Mac M1 de desenvolvimento e, depois, na instância Lightsail):
tempo até o primeiro áudio, fator de tempo real, RAM, e avaliação subjetiva com frases fixas em
pt-BR. Saída: `docs/research-log/` + ADR de escolha.

Arquitetura: `integrations/tts/` com interface `TTSProvider.synthesize(text) -> áudio em
streaming por frase`; endpoint `/voice/tts` ou WebSocket de sessão de voz; o frontend toca o
áudio e alimenta o nível da bolha (`SPEAKING`).

## Plano da 2c: escuta

- VAD no navegador (nível de energia + janela de silêncio) para começar e terminar turnos.
- STT: avaliar `faster-whisper` (MIT) em CPU (`small`/`base`) contra STT por API; medir
  latência e erro em pt-BR.
- Barge-in: falar durante `SPEAKING` corta o áudio local, cancela a síntese pendente e vai para
  `INTERRUPTED` → `LISTENING`.
- Consentimento: microfone só é aberto por ação explícita na sessão; botão sempre visível
  para encerrar; fallback para texto quando negado.
- Critério de aceite da Fase 2: conversa de vários turnos por voz no desktop e no iPhone, com
  latência ponta a ponta medida e publicada, sem prometer desempenho não demonstrado.
