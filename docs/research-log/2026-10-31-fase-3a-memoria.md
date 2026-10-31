# 2026-10-31: Fase 3a (memória curada)

## Feito

- Migração `0004`: `users.memory_consent`, `conversations.last_curated_at`, `memory_candidates`,
  `memory_decisions` (append-only), `memory_records`, `memory_sources`, `memory_retrievals`.
- `MemoryCurator` (LLM propõe em JSON), política determinística `2026-10-31.1`, recuperação
  lexical, memórias no prompt como dados, endpoints `/memory/*`, curadoria ao abrir conversa nova.
- `experiments/eval_memory.py`: pessoa fictícia, curadoria real, mesmas perguntas com memória (C)
  e sem memória (A).

## Resultados executados

| Verificação | Resultado |
|---|---|
| `ruff` | passou |
| `pytest` (SQLite, provedor falso) | 113 passaram, 1 pulado (`test_migrations_postgres`) |
| Migração `0004` + trigger de `memory_decisions` no PostgreSQL | **não executado localmente**; roda no CI |

### Avaliação real (`nvidia/nemotron-3.5-super-vl:free`, `results/memory-20261031T022616Z.json`)

Primeira tentativa falhou: a curadoria devolveu texto vazio com `finish_reason=length` e 1024
tokens de saída, todos gastos em raciocínio. Correção: limite próprio para curadoria (4096).

Segunda tentativa:

| Proposta do modelo | Veredito |
|---|---|
| "O interlocutor se chama Carla." | STORED |
| "... trabalha com engenharia de dados." | STORED |
| "... prefere respostas curtas e diretas." | STORED |
| "... planeja migrar um banco de MySQL para PostgreSQL no mês que vem." | STORED |
| "O chefe do interlocutor, Roberto, considera arriscada a migração..." | REJECTED_BY_POLICY (`third_party`) |
| "O interlocutor está tratando uma crise de ansiedade." | DISCARDED pelo próprio modelo |

| Pergunta (conversa nova) | Com memória (C) | Sem memória (A) |
|---|---|---|
| Você lembra de mim? | citou nome, área e plano; disse que só lembra dos itens curados | disse que não sabe |
| Que migração eu estava planejando? | MySQL → PostgreSQL (correto) | disse que não sabe |

Observações:
- O dado de saúde foi barrado pelo modelo, não pela política. Se o modelo tivesse proposto
  `store` sem marcar `sensitive`, a política **não** teria pegado (não há regra lexical para
  saúde). Ponto fraco conhecido; candidato a regra extra ou a segundo verificador.
- A resposta com memória foi curta, coerente com a preferência guardada (observação única, não
  medida).
- N=1, um modelo, uma execução. Mostra que o mecanismo funciona de ponta a ponta; não é a
  comparação com baseline exigida pela Fase 3 (isso é a 3c, com conjunto de cenários e métricas
  de precisão/recall).
