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
  +--- Planejamento --+                      core/planning
          |
   Policy/Approval Gate                      core/policies
          |
   Ferramentas / Busca / MCP                 integrations/*
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
