# Custos e limites

> **Como é aplicado hoje (2026-11-12).** Só provedores de preço zero são admitidos: com evidência
> de gratuidade (`VISION_LLM_FREE_GRANTS`, com validade) ou com `VISION_LLM_TRUST_ZERO_PRICE` em
> uso pessoal. Preço diferente de zero é recusado, e custo informado pelo provedor congela o razão
> (`integrations/llm/budget.py`). O limite real é de **chamadas e tokens** (`VISION_LLM_BUDGET_*`,
> por dia, por hora, por chamada e de concorrência), reservado antes de cada chamada. Os tetos em
> US$ abaixo continuam no código e nos testes, mas com preço zero ficam sempre em US$ 0: servem de
> relatório até existir um provedor pago aprovado.

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
