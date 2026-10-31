# ADR-0004: TTS com Kokoro (fp32) e voz escolhida pelo próprio agente

- Data: 2026-10-31
- Estado: aceita

## Contexto

A seção 11 do master prompt exige voz própria com pesos abertos, sem ElevenLabs, sem extrair
modelos proprietários e sem copiar vozes sem autorização. Foram medidos Kokoro e Piper em pt-BR
(`docs/research-log/2026-10-31-fase-2b-tts.md`). O responsável ouviu as amostras: **só a voz
Kokoro `pf_dora` soou aceitável**; as demais foram consideradas robóticas.

O responsável propôs que o agente escolhesse a própria voz, no mesmo espírito do nome (seção 8.1).
Também propôs extrair uma voz do ElevenLabs por engenharia reversa; isso foi recusado (viola os
termos do serviço, pode envolver voz de pessoa real sem consentimento e contraria a seção 11).

## Decisão

- **Motor:** `kokoro-onnx` 0.6.1 com o modelo **fp32** `kokoro-v1.0.onnx`. O int8 foi descartado:
  produz áudio NaN em entradas muito curtas com todas as vozes pt-BR. `KokoroTTS` recusa áudio
  inválido em vez de tocá-lo. Piper continua instalado e catalogado, mas não aprovado.
- **Papéis separados:**
  - humano = controle de qualidade: `VISION_TTS_APPROVED_VOICES` lista o que pode ser usado;
  - agente = escolha de identidade: entre as aprovadas, escolhe, adia ou recusa
    (`core/identity/voice.py`), em evento append-only `identity_voice_events`;
  - sistema = fallback objetivo: até haver escolha, a aprovada de menor latência medida,
    rotulada "padrão do sistema", nunca apresentada como escolha do agente.
- **Gatilho da deliberação:** evento real (voz ficou disponível ou a lista aprovada mudou),
  disparado por `python -m apps.api.cli voice-deliberation`. Nada de cerimônia em conversa nem
  de agenda periódica. O prompt oferece adiar e recusar como opções reais e declara que o agente
  não ouve áudio.
- **A voz não muda sozinha.** Só outra decisão registrada a altera; se a voz escolhida perder a
  aprovação, volta-se ao padrão do sistema e isso aparece como tal.
- **Entrega ao navegador:** respostas divididas em frases (`/voice/sentences`), sintetizadas uma a
  uma (`/voice/tts`, WAV), com a próxima frase sintetizada enquanto a atual toca.

## Primeira decisão do agente (instância de desenvolvimento)

`CHOSEN kokoro-dora`, justificativa: "Única opção aprovada disponível; licenciamento permissivo
(pesos Apache-2.0, runtime MIT) e métricas técnicas apresentadas são aceitáveis." Modelo:
`nvidia/nemotron-3.5-super-120b-a12b` via API da NVIDIA. Com uma só opção, a escolha real foi
entre aceitar, adiar ou recusar.

## Consequências

- ~900 MB de RAM para o Kokoro fp32 na API. Pode não caber numa instância Lightsail pequena junto
  com API e PostgreSQL; a medição na instância é pré-requisito de deploy com voz.
- 1º áudio ~2 s no Mac M1 para uma frase longa (~0,45 s para uma curta), somado à latência do LLM.
  Streaming dentro da frase fica para depois.
- Espaço para evolução: modelos abertos mais naturais (pesquisar Chatterbox Multilingual,
  F5-TTS, XTTS-v2, conferindo licença) ou voz própria com gravações autorizadas (Fase 7).
