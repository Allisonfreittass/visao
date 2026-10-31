# Custos e limites

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
