# ADR-0005: STT com faster-whisper (base) e escuta controlada pelo navegador

- Data: 2026-10-31
- Estado: aceita

## Contexto

A Fase 2 pede microfone → VAD → STT → núcleo → TTS → áudio, com barge-in, consentimento de
microfone, fallback para texto, sem escuta em segundo plano e com latência ponta a ponta medida.

## Decisão

- **STT:** `faster-whisper` 1.2.1 (MIT; modelos Systran MIT) na CPU, int8, idioma fixo `pt`,
  `beam_size=1`, sem texto condicionado ao turno anterior. Padrão `base`
  (`VISION_STT_MODEL`), escolhido pela medição: WER 6,2% em áudio limpo, 0,35 s, ~500 MB.
  `small` é mais robusto a ruído (7,5% contra 16,5%) mas leva ~1 s e ~960 MB; fica como opção.
  `av` fixado em 16.1.0 (o 19 removeu um parâmetro que o faster-whisper usa).
- **VAD no navegador**, por energia com piso de ruído adaptativo (`apps/web/src/voice/vad.ts`):
  250 ms acima do limiar para começar, 800 ms de silêncio para terminar, limiar 2,5x maior
  enquanto o agente fala (eco da própria voz). Captura PCM crua por AudioWorklet, 300 ms de
  pré-rolagem, reamostragem para 16 kHz e WAV. Um turno por vez.
- **`POST /voice/stt`** recebe o áudio de um turno, transcreve fora do event loop e não guarda o
  áudio. Tamanho limitado antes de ler o corpo.
- **Consentimento e privacidade:** o microfone só abre por clique em "Conversa por voz"; fecha ao
  encerrar, ao sair da conta e quando a página fica oculta (`visibilitychange`). Negado o
  microfone, a conversa segue por texto.
- **Barge-in:** começar a falar enquanto o agente fala interrompe a voz (estado `INTERRUPTED`), e
  essa fala vira o próximo turno.

## Alternativas consideradas

- **Web Speech API do navegador:** grátis e sem servidor, mas no Chrome o áudio vai para o
  Google, e o comportamento varia por navegador. Contraria "serviço próprio".
- **MediaRecorder (WebM/Opus):** menor upload, mas cortes no meio do fluxo não são decodificáveis
  isoladamente, o que complica a pré-rolagem. PCM + WAV é simples e exato; ~32 KB/s.
- **VAD neural (Silero) no navegador:** mais preciso com ruído, mas exige ONNX no cliente. Fica
  para quando a medição com microfone real mostrar falhas do VAD por energia.

## Consequências

- Latência mediana medida no servidor (Mac M1): STT 375 ms + LLM 2.734 ms + 1ª frase de TTS
  511 ms = 3,3 s; com os 800 ms de silêncio do VAD, ~4,1 s do fim da fala ao primeiro áudio. O LLM
  domina.
- Eco: navegadores cancelam eco parcialmente; o limiar maior durante a fala reduz falsos
  barge-ins, mas fones de ouvido continuam sendo o modo mais confiável.
- iPhone: `getUserMedia` exige HTTPS fora de `localhost`; testar no celular depende de servir a
  interface com TLS (Cloudflare na implantação, ou túnel local).
