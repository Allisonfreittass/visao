# ADR-0002: Qwen via API compatível com OpenAI, com preço obrigatório

- Data: 2026-10-31
- Estado: aceita (família do modelo); provedor de inferência e versão exata **pendentes**

## Contexto

A Fase 1b precisa de um LLM real. O responsável pelo projeto escolheu a família **Qwen**.
Hospedar o modelo no Lightsail não é viável; a inferência começa via API.

## Decisão

- Família: Qwen. Candidato preferido: um modelo de **pesos abertos sob Apache-2.0** (ex.:
  Qwen3.8-27B, segundo fontes de terceiros de ago–out/2026), porque mantém aberta a opção de
  hospedagem própria futura. Versão exata e licença a confirmar no model card oficial.
- Integração: um único `OpenAICompatibleProvider` para `/chat/completions`. Alibaba Cloud Model
  Studio, OpenRouter, DeepInfra e servidores próprios (vLLM) expõem esse formato, então trocar
  de host é só configuração.
- **Preço por token é configuração obrigatória.** Sem ele o provedor fica desligado: não dá para
  medir nem limitar gasto de algo cujo custo não se conhece. Nenhum preço fica no código.
- Orçamentos diário e por conversa são verificados no código antes de cada chamada, e todas as
  chamadas (inclusive falhas) ficam em `model_usage`.

## Alternativas consideradas

- **SDK oficial de cada provedor**: acopla o código ao host; descartado.
- **Biblioteca multi-provedor (LiteLLM etc.)**: muita superfície para o que é um POST; pode ser
  reavaliada quando houver streaming e tool calling.
- **Preço embutido numa tabela no código**: as fontes encontradas divergem entre si e os preços
  mudam; risco alto de custo registrado errado.

## Consequências

- O provedor só faz `complete` (sem streaming, tools, saída estruturada nem cancelamento). Isso
  é uma lacuna conhecida em relação à seção 6 do master prompt; streaming entra com a voz
  (Fase 2), tools com a pesquisa (Fase 4).
- O orçamento é verificado antes da chamada: uma única resposta pode ultrapassar o teto em no
  máximo o custo de `VISION_LLM_MAX_OUTPUT_TOKENS`.

## Fontes consultadas (terceiros, não oficiais; conferir antes de usar os números)

- https://the-decoder.com/alibabas-qwen-team-releases-qwen-3-8-models-with-open-weights-under-the-apache-2-0-license/
- https://www.yottalabs.ai/post/qwen-3-8-max-release-date-specs-how-to-access-2026
- https://www.cloudzero.com/blog/qwen-api-pricing/
- https://www.mercatus-ai.com/blog/qwen-api-pricing

## Adendo (2026-10-31): modelo em uso e provedor de reserva

- Para custo zero, o modelo em uso passou a ser `nvidia/nemotron-3.5-super-vl` (120B, 12B ativos)
  no plano grátis do OpenRouter. Qwen continua sendo a família preferida; nenhum Qwen estava
  grátis no OpenRouter nesta data.
- O plano grátis do OpenRouter limita a 50 requisições/dia. Foi adicionado um
  `FallbackLLMProvider`: o principal é tentado primeiro e, em cota esgotada, 429, erro 5xx,
  timeout, erro de rede ou resposta malformada, a chamada vai para a reserva (API da NVIDIA,
  mesmo modelo). Erros de configuração (401, 400, 404) não acionam a reserva, para não esconder
  chave errada. Um provedor com cota esgotada é pulado por 15 minutos.
- Cota diária esgotada é detectada pelos cabeçalhos `X-RateLimit-Remaining: 0` e
  `X-RateLimit-Reset` e falha na hora, sem novas tentativas.
- O custo de cada chamada passou a vir de quem respondeu (`LLMResponse.cost_usd`).
