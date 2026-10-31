# Autonomia: metas, iniciativas e limites

> Estado: **Fase 5 implementada; ciclo autônomo na Fase 9** (seção no fim). Primeira coisa que o sistema faz sem mensagem do usuário:
> retomar uma pergunta de fato público que ficou sem resposta, **só depois de aprovação**.

## Princípios

1. **Proposta não é permissão.** O agente propõe; só o dono aprova; a aprovação vale apenas para
   as permissões que a meta declarou.
2. **Gatilhos reais.** Iniciativas nascem de eventos registrados (pesquisa inconclusiva ou adiada
   por orçamento), nunca de agenda arbitrária nem de "vida interior" simulada.
3. **Permissões em código, conferidas duas vezes:** na avaliação da proposta e de novo pelo worker
   na hora de executar.
4. **Pausa geral.** `PUT /system/autonomy {"paused": true}` (ou o interruptor na interface) para
   tudo que é por iniciativa própria: o worker não pega trabalho, a curiosidade não propõe metas,
   nenhum aviso é criado. A conversa continua.
5. **Tudo tem motivo registrado:** cada transição de meta (append-only) e cada trabalho na fila
   guardam por quê.

## Ciclo de vida das metas

```text
PROPOSED -> EVALUATED -> APPROVED -> ACTIVE -> COMPLETED
   |            |            |          |-> FAILED
   v            v            v          |-> PAUSED <-> ACTIVE
REJECTED     REJECTED     CANCELLED     '-> CANCELLED
```

Avaliação (política em código, `core/goals/lifecycle.py`): exige critério de sucesso, só aceita
permissões de `{web_research, llm, notify}`, limita orçamento (≤ 5 buscas, ≤ 3 chamadas de LLM) e
exige um executor conhecido. Enviar mensagens fora do app, gastar dinheiro, mexer em
infraestrutura: rejeitado.

## A iniciativa existente: `research_followup`

1. Evento: lacuna de fato público com valor esperado ≥ 0,6 fica `INCONCLUSIVE` ou `DEFERRED`.
2. Proposta (uma por lacuna), avaliada e listada em `GET /approvals`; a resposta daquele turno
   menciona que há uma proposta aguardando aprovação.
3. Aprovação (`POST /goals/{id}/approve`) enfileira um trabalho idempotente.
4. Worker: confere estado e permissões, respeita o orçamento diário de pesquisas (senão adia para
   o dia seguinte), pesquisa com até 2 consultas, pede ao LLM para julgar se os trechos
   **respondem explicitamente** à pergunta.
5. Respondeu → resumo com citações vira aviso (`GET /notifications`) e a meta fica `COMPLETED` com
   evidência. Não respondeu → `FAILED`, **sem aviso**.

## Fila e worker

- Fila no próprio banco (`scheduled_jobs`), sem Redis: chave de idempotência única, captura
  otimista com prazo (lease de 5 min), tentativas limitadas com espera exponencial (30 s, 60 s…),
  fila de mortos (`DEAD`), retomada de trabalho de worker que caiu, adiamento sem gastar tentativa.
- Processo: `python -m apps.worker.main` (serviço `worker` no Docker Compose). Dorme quando ocioso
  ou pausado; para limpo em SIGTERM. Nenhum LLM roda sem trabalho criado por evento.
- Auditoria: `GET /initiatives` lista os trabalhos do usuário com o motivo de cada um.

## Avisos

- Só dentro do app por enquanto (`GET /notifications`, painel na interface). Push para iPhone
  exige HTTPS e entra com a implantação.
- Horário silencioso por usuário (padrão 22:00–08:00, `America/Sao_Paulo`;
  `PUT /notifications/settings`): avisos criados nessa janela só aparecem quando ela termina.
- No máximo 5 avisos por 24 h por usuário.

## Limitações conhecidas

- Uma única iniciativa implementada; metas criadas pelo usuário (`origin=user`) existem no modelo
  mas ainda não há rota para criá-las.
- A pausa é global, não por usuário (adequado ao uso single-user atual).
- `PROPOSE_GOAL` não é uma ação direta da curiosidade: a proposta acontece depois, a partir do
  resultado (inconclusivo/adiado).

## Ciclo autônomo (Fase 9)

`core/autonomy/cycle.py`. Disparado por agenda, com um job `cognitive_cycle` idempotente por
janela de `VISION_AUTONOMY_CYCLE_MINUTES` (padrão 60). Nunca é um laço contínuo. Detectar
oportunidades só lê o banco; o modelo só é chamado para executar.

| Oportunidade | Ação | Precisa de |
|---|---|---|
| lacuna de fato público `DEFERRED`/`INCONCLUSIVE` | propõe meta de retomada | nada (propor é grátis) |
| meta avaliada | aprova por permissão permanente e pesquisa | `auto_research` ligado pelo dono |
| conversa sem mensagens há 30 min e sem reflexão | reflexão | orçamento |
| nome `null`, ≥ 3 conversas, ≥ 1 dia desde o genesis, sem deliberação nos últimos 30 dias | agenda deliberação de nome | orçamento |

Limites, todos aplicados em código:

- **Pausa global:** não roda nada.
- **Orçamento de autonomia:**
  - `VISION_AUTONOMY_LLM_CALLS_PER_DAY`, padrão 20;
  - `VISION_AUTONOMY_TOKENS_PER_DAY`, padrão 60000;
  - `VISION_AUTONOMY_MAX_ACTIONS_PER_CYCLE`, padrão 3;
  - `VISION_AUTONOMY_MAX_SECONDS`, padrão 120.

  O orçamento conta só os propósitos autônomos (`name_deliberation`, `followup_summary`,
  `reflection`). Com orçamento zero, nada que chama o modelo roda.
- **`auto_research`:** desligado por padrão. Só o dono liga, pelo painel de iniciativas ou por
  `PUT /autonomy/permissions`. Sem ele, a meta espera aprovação em `/approvals`.
- **Registro:** cada ação vira uma linha em `decisions` com `origin=autonomous`, visível em
  `GET /decisions`.
