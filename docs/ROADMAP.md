# Roadmap

Cada fase só começa depois que a anterior passa no seu critério de aceite, com testes
executados de verdade. "Passou" significa que o comando rodou e o resultado está registrado.

| Fase | Escopo | Critério de aceite | Estado |
|---|---|---|---|
| 0. Fundação | repo, Docker, PostgreSQL, migrações, auth, CI, testes, health checks, docs | `docker compose up` sobe e os testes passam | **em andamento** (ver abaixo) |
| 1. Genesis e conversa | UUID técnico, `chosen_name = null`, identidade mínima, `LLMProvider`, chat persistente, histórico de nomes | primeira sessão sem memórias prévias, nenhum nome imposto, segunda sessão recupera só experiências reais | não iniciada |
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

Pendente para fechar a Fase 0:
- **Executar `docker compose up` de verdade.** A máquina de desenvolvimento atual não tem
  Docker instalado; o compose foi escrito mas não foi executado.
- Rodar a suíte contra PostgreSQL (só roda no CI ou com `VISION_TEST_DATABASE_URL`).
- Repositório remoto e primeira execução do CI.
- Frontend React + TypeScript (esqueleto): adiado para o início da Fase 1, quando houver tela útil.
- Worker persistente: adiado para a Fase 1/5, quando houver job real (evitar stub vazio).

## Próximo incremento proposto

**Fase 1a: Genesis.** Tabelas `agent_identities`, `identity_name_events`, `identity_versions`;
comando `python -m apps.api.cli genesis` idempotente (recusa recriar sem confirmação + backup);
`GET /system/status` com `internal_id`, `chosen_name: null`, `genesis_version: "2.1"`;
testes de aceite da seção 2 e 8.1.

Dependências: Fase 0 validada com Docker; nenhuma credencial externa necessária.
Fase 1b (conversa) depende da escolha do provedor de LLM e de uma chave de API com limite de
gasto (ver [MODEL_SELECTION.md](MODEL_SELECTION.md) e [COSTS.md](COSTS.md)).
