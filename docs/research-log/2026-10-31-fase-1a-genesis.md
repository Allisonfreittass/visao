# 2026-10-31: Fase 1a (Genesis)

## Feito

- Identidade mínima: `agent_identities`, `identity_versions` (genesis = versão 1),
  `identity_name_events`. Migração `0002` com triggers append-only (PostgreSQL e SQLite).
- `genesis` na CLI (idempotente, sem reset) e `GET /system/status`.
- Registro auditado de decisões de nome. Nenhum código de produção chama esse registro ainda.
- Varredura estática contra identidade imposta (nome VISÃO, nome literal, pedido de escolha de
  nome, traços de persona). É heurística: pega os casos óbvios, não prova ausência.

## Resultados executados

| Verificação | Resultado |
|---|---|
| `ruff check .` / `ruff format --check .` | passou |
| `pytest` (SQLite) | 48 passaram, 1 pulado (`test_migrations_postgres`) |
| Smoke manual: `alembic upgrade head` → `genesis --status` (vazio) → `genesis` → `genesis` de novo (mesmo UUID, nada alterado) → login → `/system/status` com `chosen_name: null` → `alembic downgrade base` | passou (SQLite) |
| Triggers append-only e migração `0002` no PostgreSQL | **não executado localmente**; roda no CI |

## Decisões

- O UUID técnico é a própria chave primária de `agent_identities`.
- Não existe reset de genesis. Será criado só junto com backup verificado.
- `name_history` é derivado dos eventos `CHOSEN`/`CHANGED`, não guardado em coluna.
- `personality_profile` não virou coluna: é `null` por definição e não tem uso até a Fase 6.
