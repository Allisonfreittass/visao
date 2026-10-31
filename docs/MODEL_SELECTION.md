# Seleção de modelos (LLM, STT, TTS)

> **Nenhum benchmark foi executado.** Esta página lista candidatos com base em conhecimento
> prévio (até meados de 2026). Licenças, versões, preços e suporte a pt-BR **precisam ser
> reconferidos na fonte oficial no dia da escolha**; marcados como ⚠️ quando a dúvida é maior.
> Nenhuma escolha final foi feita.

## Critérios comuns

1. Licença compatível com uso pessoal de pesquisa e, idealmente, comercial futuro.
2. Qualidade real em português brasileiro (testada por nós, não pelo marketing).
3. Custo medido por conversa/minuto.
4. Requisitos de hardware compatíveis com Lightsail pequeno (CPU) ou API externa.
5. Recursos: streaming, tool calling, saída estruturada, contexto.

## LLM

> **Decisão (2026-10-31): família Qwen**, via API compatível com OpenAI. Provedor de inferência
> e versão exata ainda pendentes. Ver [ADR-0002](decisions/0002-qwen-via-api-compativel-openai.md).

Inferência **via API** no início. Hospedar LLM grande no Lightsail não é viável.

| Candidato | Tipo | Licença (a confirmar) | Observações |
|---|---|---|---|
| Qwen (família 2.5/3) via provedor de inferência | pesos abertos | maioria Apache-2.0; alguns tamanhos com licença própria ⚠️ | bom multilíngue; tool calling depende do provedor |
| Gemma (família 2/3) via provedor | pesos abertos | Gemma Terms of Use (não é OSI) ⚠️ | checar restrições de uso |
| Llama (3.x/4) via provedor | pesos abertos | Llama Community License ⚠️ | cláusulas de atribuição/uso |
| Claude (Anthropic) via API | proprietário | termos comerciais | forte em pt-BR e tool use; custo maior |
| Outros modelos de API | proprietário | termos comerciais | avaliar só se o benchmark justificar |

Plano de avaliação (Fase 1): conjunto fixo de ~50 tarefas em pt-BR (conversa, tool calling,
saída JSON, calibração de incerteza), mesmo prompt de sistema mínimo, métricas de custo e
latência registradas em `model_usage`. Escolha documentada em ADR.

Requisito arquitetural já fixado: `LLMProvider` com geração, streaming, tools, saída
estruturada, cancelamento, retries, timeouts e contabilização de custo. Trocar o provedor não
toca no estado cognitivo.

## STT

| Candidato | Licença (a confirmar) | Observações |
|---|---|---|
| Whisper (OpenAI, pesos) | MIT | pt-BR razoável; modelos grandes lentos em CPU |
| faster-whisper (CTranslate2) | MIT | int8 em CPU; `small`/`medium` podem caber no Lightsail ⚠️ latência |
| whisper.cpp | MIT | alternativa C/C++ em CPU |
| STT por API (vários) | comercial | menor latência, custo por minuto |

VAD: Silero VAD (MIT ⚠️) ou o VAD do próprio navegador/WebRTC.

## TTS (sem ElevenLabs)

| Candidato | Licença (a confirmar) | pt-BR | Observações |
|---|---|---|---|
| Piper | código migrou para GPL-3.0 (piper1-gpl) ⚠️; vozes com licenças individuais | há vozes pt-BR | muito leve, roda em CPU em tempo real; naturalidade limitada |
| Kokoro (82M) | pesos Apache-2.0 | há vozes pt-BR (poucas) ⚠️ | leve, qualidade boa para o tamanho; fonemização via espeak-ng (GPL) ⚠️ |
| F5-TTS | código MIT; **pesos pré-treinados CC-BY-NC** ⚠️ | depende de fine-tune | clonagem zero-shot; não comercial; GPU recomendada |
| XTTS-v2 (Coqui) | Coqui Public Model License (não comercial) ⚠️ | sim | empresa encerrou; licença restritiva |

Recomendação provisória para benchmark da Fase 2: **Kokoro e Piper em CPU** como primeiros
candidatos (licenças mais permissivas e hardware compatível), F5-TTS só como pesquisa de
identidade vocal com dados autorizados. "Serviço próprio com pesos abertos" ≠ "sintetizador
treinado do zero".

## Pendências

- [ ] Reconferir todas as licenças acima na fonte oficial.
- [ ] Medir qualidade pt-BR de cada TTS com frases-teste fixas.
- [ ] Medir latência real (primeiro áudio) na instância Lightsail após auditoria.
- [ ] Definir provedor de inferência do LLM e preço por token vigente.
