# Custos e limites

> **Como é aplicado hoje (2026-11-12).** A produção usa o Claude Haiku 5.5 (US$ 0,10 / 0,50 por
> milhão de tokens). Provedor pago só entra com os dois tetos acima de zero
> (`VISION_LLM_PAID_DAILY_USD`, `VISION_LLM_PAID_MONTHLY_USD`; hoje US$ 0,50/dia e US$ 10/mês).
> Antes de cada chamada o razão (`integrations/llm/budget.py`) reserva o pior caso (tokens de
> entrada estimados e o máximo de saída, no preço configurado) e recusa se passar do teto; depois
> acerta pelo custo real e devolve a sobra. Provedor que informa mais do que o reservado congela o
> razão. Com os tetos em zero vale a regra antiga: só preço zero, com evidência ou
> `VISION_LLM_TRUST_ZERO_PRICE`. Os limites de chamadas e tokens (`VISION_LLM_BUDGET_*`) valem
> nos dois casos. Configure também o limite de gasto no console da Anthropic.

> Valores **propostos**, não medidos. Nenhum custo foi observado ainda. Atualizar com dados
> reais de `model_usage` a partir da Fase 1.

## Infraestrutura existente

| Item | Custo informado | Verificado? |
|---|---|---|
| AWS Lightsail | ~US$ 12/mês | não (recursos, uso e workloads não auditados) |
| Cloudflare | plano atual não informado | não |
| Créditos AWS | ~US$ 100 | **não**: confirmar saldo, vencimento e se cobrem Lightsail |

Créditos AWS **não** pagam APIs de terceiros (LLM, STT, TTS, busca).

## Orçamento proposto para APIs (a aprovar)

| Limite | Valor proposto | Comportamento ao atingir |
|---|---|---|
| Teto mensal total de APIs | US$ 20 | pausa tudo que não é conversa ativa; avisa |
| Teto diário | US$ 1,50 | pausa iniciativas e pesquisas proativas |
| Por conversa | US$ 0,30 | resposta curta + aviso, sem ferramentas caras |
| Por pesquisa web (lacuna) | 5 buscas, 10 páginas | marca lacuna como `INCONCLUSIVE` ou `DEFERRED` |
| Iniciativas proativas | 3/dia, fora do horário silencioso | adia |
| Reflexão | 1 ciclo por conversa encerrada | não reflete |
| Curadoria de memória | 1 chamada por conversa encerrada, só com consentimento | mensagens ficam pendentes |

Além disso: configurar **limite de gasto no painel de cada provedor** (defesa independente do
código).

## Degradação segura

1. Sem orçamento → pausar curiosidade proativa e reflexão.
2. Preservar memória e histórico sempre.
3. Manter funcionalidades locais (consulta a memórias, histórico, TTS local se instalado).
4. Nunca "fingir" resposta quando o LLM está indisponível: informar indisponibilidade.

## O que medir

Tokens de entrada/saída por chamada, segundos de STT/TTS, buscas, páginas baixadas,
CPU/RAM/disco/rede da instância. Tudo em `model_usage` e métricas de sistema.
