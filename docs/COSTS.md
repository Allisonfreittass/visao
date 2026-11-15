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

## Chamadas pequenas por conversa (15/11/2026)

| Chamada | Quando | Tamanho | Orçamento |
|---|---|---|---|
| Título da conversa (`conversation_title`) | uma vez, depois da primeira troca, pelo worker; tenta de novo nos turnos seguintes até 8 mensagens | ~4 mensagens de até 600 caracteres na entrada, 24 tokens de saída | reserva no `budget.py` e no orçamento da conversa; sem orçamento, fica a data |
| Página da oferta de painel | só quando você aprova | como qualquer página (`VISION_ARTIFACT_MAX_OUTPUT_TOKENS`) | igual às páginas |

No Haiku 5.5 o título custa bem menos de US$ 0,001, mas conta **uma chamada** no limite de
chamadas por dia e por hora (`VISION_LLM_BUDGET_CALLS_*`, padrão 30/dia e 10/hora). Um turno com
navegador já usa de 3 a 5 chamadas (planejar, responder, conferir as regras...).

## Painéis vivos (conferência diária)

Por painel ativo e por dia:
- 2 páginas no navegador (`VISION_PANEL_MAX_PAGES`), sem custo de API;
- 1 chamada de extração: entrada de até ~4 mil tokens (2 páginas de até 7 mil caracteres), saída
  de até 900 tokens.

No Haiku 5.5 (US$ 0,10 / 0,50 por milhão), o pior caso é cerca de US$ 0,0009 por conferência.
Com 3 painéis (o padrão), dá menos de US$ 0,003 por dia, ou ~US$ 0,09 por mês.

O que pesa mais é o **limite de chamadas**: cada conferência gasta 1 das chamadas diárias da
autonomia (`VISION_AUTONOMY_LLM_CALLS_PER_DAY`) e 1 das chamadas por dia e por hora do razão.

Criar ou editar um painel pela conversa gasta 1 chamada a mais (extração ou edição), no orçamento
da conversa.

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
