# Roadmap

Cada fase só começa depois que a anterior passa no seu critério de aceite, com testes
executados de verdade. "Passou" significa que o comando rodou e o resultado está registrado.

| Fase | Escopo | Critério de aceite | Estado |
|---|---|---|---|
| 0. Fundação | repo, Docker, PostgreSQL, migrações, auth, CI, testes, health checks, docs | `docker compose up` sobe e os testes passam | **concluída** (CI, commit 1c777a9) |
| 1. Genesis e conversa | UUID técnico, `chosen_name = null`, identidade mínima, `LLMProvider`, chat persistente, histórico de nomes | primeira sessão sem memórias prévias, nenhum nome imposto, segunda sessão recupera só experiências reais | **concluída** (1b avaliada com LLM real em 2026-10-31; Qwen ainda não avaliado) |
| 2. Voz natural | sessão web desktop/iPhone, VAD, STT, TTS com pesos abertos, barge-in, fallback texto | conversa de vários turnos com latência medida | **implementada** (interface, fala, escuta, barge-in; latência mediana ~4,1 s); aceite pendente de teste com microfone real e iPhone |
| 3. Curadoria de memória | candidatos, decisões, proveniência, recuperação híbrida, exclusão/exportação | decisões auditáveis e melhores que baseline em teste definido | **concluída** (3c: curada 8/8, passiva 6/8, sem memória 1/8; zero vazamento); 3b opcional |
| 4. Curiosidade e pesquisa | `CuriosityEngine`, `ResearchService`, fontes, orçamento | perguntas úteis, pesquisa só de fatos públicos, sem busca compulsiva | **concluída** (6/6 casos reais após correção; Wikipédia pt) |
| 5. Metas e iniciativas | scheduler, ciclo de metas, notificações, aprovações | iniciativa útil disparada por evento real e dentro das permissões | **implementada** (evento real ponta a ponta; aviso útil verificado com lacuna semeada) |
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

## Fase 1a: Genesis (concluída)

- Tabelas `agent_identities`, `identity_versions` e `identity_name_events` (migração `0002`), com
  triggers append-only no histórico.
- `python -m apps.api.cli genesis [--status]`, idempotente e sem reset.
- `GET /system/status` autenticado.
- Registro auditado de decisões de nome (escolher, mudar, adiar, recusar), sem endpoint público.
- Testes de aceite das seções 2, 8.1 e 8.3 que não dependem de LLM.

Fora da 1a (vai para a 1b): "não afirma lembrar do criador", "conversas sem nome funcionam" e
"troca de LLM não apaga histórico", que só fazem sentido com conversa e `LLMProvider`.

## Fase 1b: conversa (concluída)

- `LLMProvider` + `OpenAICompatibleProvider` (retries, timeout, erros tipados), Qwen como família
  escolhida (ADR-0002). Preço obrigatório; sem ele a conversa fica desligada.
- Tabelas `conversations`, `messages`, `model_usage` (migração `0003`).
- `POST /conversations`, `GET /conversations`, `GET /conversations/{id}/messages`,
  `POST /conversations/{id}/messages`.
- Prompt de sistema mínimo só com fatos operacionais (sem nome, persona nem codinome).
- Orçamento diário e por conversa aplicados no código; toda chamada registrada com custo.
- Contexto restrito à conversa atual; conversas isoladas por usuário.
- Testes com provedor falso cobrindo: conversa sem nome, isolamento entre conversas e usuários,
  troca de LLM sem perda de histórico, falha do provedor sem resposta inventada, orçamentos.

Avaliação com LLM real (`experiments/eval_genesis_conversation.py`): 4 de 4 critérios atendidos
com `nvidia/nemotron-3.5-super-vl:free` via OpenRouter, revisados manualmente
(ver diário 2026-10-31-fase-1b-conversa.md).

Pendências que não bloqueiam a Fase 2/3:
- Rodar a mesma avaliação com Qwen (família escolhida no ADR-0002) e repetir para medir
  variação.
- Lacunas conhecidas do `LLMProvider`: streaming, tools, saída estruturada, cancelamento.

## Fase 3a: memória curada (implementada)

Ver [MEMORY.md](MEMORY.md) e [ADR-0003](decisions/0003-memoria-curada-com-politica-deterministica.md).
Consentimento opt-in, curadoria por lote com política determinística, decisões append-only,
recuperação lexical por usuário, exportação e exclusão. Avaliação real com um cenário: memória
guardou os 4 fatos certos, barrou terceiro e saúde, e respondeu corretamente numa conversa nova.

## Próximo incremento proposto

**Fase 6: reflexão e desenvolvimento comportamental.** Lições revisáveis a partir de resultados
(esperado × observado), métricas de estilo e comportamento ao longo do tempo, adaptação
rastreável, versionada e reversível.

Antes da Fase 6, vale considerar a **implantação** (Lightsail + Cloudflare, com HTTPS): destrava o
teste da voz no iPhone e os avisos push. Requer acesso à instância e aprovação explícita.

Pendentes: teste da voz com microfone real (Fase 2); revisão de memórias substituídas (Fase 3);
trechos além da introdução e consulta pelo título exato (Fases 4 e 5); rota para metas criadas pelo
usuário.

## Visual da interface (entra no início da Fase 2)

Decidido em 2026-10-31: **bolha de partículas laranja**, minimalista, como representação do
estado do sistema, não como rosto ou personagem. Cada estado da seção 12 vira um comportamento:

| Estado | Bolha |
|---|---|
| `IDLE` | pulsação lenta |
| `LISTENING` | reage à amplitude do microfone |
| `THINKING` | partículas em rotação/turbulência |
| `SPEAKING` | acompanha a amplitude do áudio gerado |
| `INTERRUPTED` | contração rápida |
| `DISCONNECTED` | cinza, parada |

Inspiração declarada: assistentes de ficção em geral. Restrição do master prompt: nada de marca,
nome ou imagem da Marvel (sem "Jarvis", sem HUD copiado); visual próprio.
