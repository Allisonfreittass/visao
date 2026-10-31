# Roadmap

Cada fase só começa depois que a anterior passa no seu critério de aceite, com testes
executados de verdade. "Passou" significa que o comando rodou e o resultado está registrado.

| Fase | Escopo | Critério de aceite | Estado |
|---|---|---|---|
| 0. Fundação | repo, Docker, PostgreSQL, migrações, auth, CI, testes, health checks, docs | `docker compose up` sobe e os testes passam | **concluída** (CI, commit 1c777a9) |
| 1. Genesis e conversa | UUID técnico, `chosen_name = null`, identidade mínima, `LLMProvider`, chat persistente, histórico de nomes | primeira sessão sem memórias prévias, nenhum nome imposto, segunda sessão recupera só experiências reais | **1a concluída localmente**; 1b não iniciada |
| 2. Voz natural | sessão web desktop/iPhone, VAD, STT, TTS com pesos abertos, barge-in, fallback texto | conversa de vários turnos com latência medida | não iniciada |
| 3. Curadoria de memória | candidatos, decisões, proveniência, recuperação híbrida, exclusão/exportação | decisões auditáveis e melhores que baseline em teste definido | não iniciada |
| 4. Curiosidade e pesquisa | `CuriosityEngine`, `ResearchService`, fontes, orçamento | perguntas úteis, pesquisa só de fatos públicos, sem busca compulsiva | não iniciada |
| 5. Metas e iniciativas | scheduler, ciclo de metas, notificações, aprovações | iniciativa útil disparada por evento real e dentro das permissões | não iniciada |
| 6. Reflexão e comportamento | lições revisáveis, métricas de estilo, comparação longitudinal | mudanças observáveis, atribuíveis e reversíveis | não iniciada |
| 7. Pesquisa avançada | fine-tuning, TTS próprio, continual learning | só após baselines e datasets | não iniciada |

## Fase 0: o que está feito e o que falta

Feito:
- Layout do repositório conforme a seção 21 do master prompt.
- API FastAPI: `/health`, `/ready`, `/auth/login`, `/auth/me`.
- Usuários com Argon2id, JWT, trilha de auditoria.
- Alembic com migração inicial (`users`, `audit_logs`).
- Dockerfile + `docker-compose.yml` (API + PostgreSQL/pgvector).
- CI (GitHub Actions) com lint e testes contra SQLite e PostgreSQL.
- Documentação inicial e ADR-0001.

Validação:
- CI do commit `1c777a9` passou (lint, testes contra SQLite e PostgreSQL, `docker compose up`
  com `/ready` respondendo), conforme relatado em 2026-10-30.

Adiado para fases seguintes:
- Frontend React + TypeScript (esqueleto): início da Fase 1, quando houver tela útil.
- Worker persistente: Fase 1/5, quando houver job real (evitar stub vazio).
- `docker compose up` na máquina local (Docker ainda não instalado aqui).

## Fase 1a: Genesis (concluída localmente; CI pendente)

- Tabelas `agent_identities`, `identity_versions` e `identity_name_events` (migração `0002`), com
  triggers append-only no histórico.
- `python -m apps.api.cli genesis [--status]`, idempotente e sem reset.
- `GET /system/status` autenticado.
- Registro auditado de decisões de nome (escolher, mudar, adiar, recusar), sem endpoint público.
- Testes de aceite das seções 2, 8.1 e 8.3 que não dependem de LLM.

Fora da 1a (vai para a 1b): "não afirma lembrar do criador", "conversas sem nome funcionam" e
"troca de LLM não apaga histórico", que só fazem sentido com conversa e `LLMProvider`.

## Próximo incremento proposto

**Fase 1b: conversa.** `LLMProvider` com um provedor real, tabelas `conversations` e `messages`,
`model_usage` com custo por chamada, prompt de sistema mínimo (sem nome nem persona, coberto pela
varredura), `POST /conversations` e `POST /conversations/{id}/messages`, e os testes de aceite
pendentes acima.

Dependências: **escolha do provedor de LLM e uma chave de API com limite de gasto configurado no
painel** (decisão sua; ver [MODEL_SELECTION.md](MODEL_SELECTION.md) e [COSTS.md](COSTS.md)).
