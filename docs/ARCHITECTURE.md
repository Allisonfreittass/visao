# Arquitetura

## Princípio central

**O agente experimental não é o LLM.** Identidade operacional, memórias, metas, decisões,
políticas e avaliações vivem no PostgreSQL e no código do Cognitive Core. O LLM é um componente
substituível atrás de `LLMProvider`. Trocar de modelo nunca apaga estado.

## Forma

Monólito modular (FastAPI) + worker persistente, com Docker Compose. Sem Kubernetes, sem
microsserviços. Redis só entra com justificativa medida (ver ADR futura).

```text
Web/iPhone (sessão de voz e texto)
          |
     Cloudflare (DNS, TLS, WAF, rate limiting)
          |
 FastAPI + autenticação                      apps/api
          |
     Cognitive Core                          core/*
  |       |        |
Memória  Metas   Curiosidade                 core/memory, core/goals, core/curiosity
  |       |        |
  +--- Decisão e ciclo autônomo --+         core/decision, core/autonomy, core/mind
          |
   Policy/Approval Gate                      core/policies
          |
   LLM / Busca / Voz / Web Push              integrations/*
          |
     Observação
          |
 Reflexão e Curadoria                        core/reflection, core/memory
          |
 PostgreSQL + trilha de auditoria            infrastructure/database

Workers agendados --> eventos --> Cognitive Core      apps/worker, infrastructure/jobs
LLM Provider <--> Cognitive Core                      integrations/llm
STT/TTS <--> Sessão de voz                            integrations/stt, integrations/tts
```

## Camadas e regras de dependência

| Camada | Pode depender de | Não pode depender de |
|---|---|---|
| `apps/*` (entrada: HTTP, worker) | `core`, `integrations`, `infrastructure` | — |
| `core/*` (domínio cognitivo) | interfaces (`Protocol`) de integrações, `infrastructure.database` | FastAPI, SDKs de terceiros |
| `integrations/*` (LLM, busca, STT, TTS, MCP) | bibliotecas externas | `apps` |
| `infrastructure/*` (DB, jobs, observabilidade) | SQLAlchemy, Alembic, logging | `apps` |

Permissões são aplicadas **no código** (`core/policies`), nunca só no prompt.

## O que existe na Fase 0

- `apps/api`: FastAPI com `/health`, `/ready`, `/auth/login`, `/auth/me`, CLI `create-user`.
- `infrastructure/database`: engine/sessão SQLAlchemy 2, modelos `users` e `audit_logs`.
- `migrations/`: Alembic com migração inicial.
- `infrastructure/observability`: logging estruturado em JSON, sem conteúdo sensível.
- Docker Compose com PostgreSQL 16 + pgvector (porta presa a `127.0.0.1`).
- CI no GitHub Actions: lint + testes contra SQLite e PostgreSQL.

Os demais diretórios existem só como pacotes vazios para fixar o layout; **não contêm
funcionalidade** e não devem ser apresentados como tal.

## Dados

- Datas sempre em UTC (`timestamptz`).
- IDs: UUID v4 gerados na aplicação.
- Migrações versionadas; toda migração tem `downgrade`.
- `audit_logs` registra ações relevantes (login, criação de usuário) sem senha nem token.

## Segurança na Fase 0

- Senhas com Argon2id; tokens JWT HS256 com expiração curta.
- `VISION_SECRET_KEY` obrigatória fora de `development`/`test`; a aplicação recusa iniciar com o
  valor padrão em produção.
- PostgreSQL nunca exposto publicamente.
- Rate limiting fica a cargo da Cloudflare na borda; limite na aplicação entra antes do primeiro
  deploy público.

## Implantação alvo (não executada)

AWS Lightsail existente (~US$ 12/mês) + Cloudflare. **Nenhum recurso foi inspecionado ainda**:
CPU, RAM, disco, containers e serviços em execução precisam ser auditados antes de qualquer
instalação. Nenhum deploy sem aprovação explícita. Ver [COSTS.md](COSTS.md).

## Fase 9: camada de decisão e ciclo autônomo

A decisão fica separada da expressão. O LLM redige a resposta, mas **o que o sistema fez** no turno
é decidido e registrado em código (`decisions`), e só esses fatos entram no prompt.

```text
mensagem (texto ou voz)
   |
run_turn  (core/decision/pipeline.py)
   |-- manifesto de capacidades      core/identity/capabilities.py   (o que existe de fato)
   |-- curiosidade (lê memórias)     core/curiosity/engine.py        ask / search / ignore
   |-- continuidade                  core/autonomy/continuity.py     lacunas de outras conversas
   |-- pergunta sobre nome?          core/identity/name_deliberation.py -> job name_deliberation
   |-- TurnPlan: ações executadas -> "fatos do turno" no prompt
   |-- reply (LLM = expressão)       core/conversation/service.py
   |-- curadoria de memória
   '-- Decision(origin=turn)         tabela decisions

worker (a cada VISION_AUTONOMY_CYCLE_MINUTES, 1 job idempotente por janela)
   '-- run_cycle (core/autonomy/cycle.py), respeitando pausa e orçamento de autonomia
         1. lacunas de fato público adiadas -> propõe meta -> pesquisa se auto_research
         2. conversas paradas há 30 min -> reflexão
         3. nome em aberto (>= 3 conversas, >= 1 dia, a cada 30 dias) -> deliberação
         cada ação -> Decision(origin=autonomous)
```

Inspeção: `GET /decisions`, `GET /cognition/metrics`, `GET /identity/name`,
`GET|PUT /autonomy/permissions`. Ver [AUTONOMY.md](AUTONOMY.md) e
[research/curiosity_evaluation.md](research/curiosity_evaluation.md).
