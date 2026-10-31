# VISÃO

Pesquisa experimental pessoal sobre arquitetura cognitiva persistente: memória autobiográfica,
curadoria de memória, busca orientada por incerteza, reflexão e metas persistentes em torno de
um LLM substituível.

> **VISÃO é o codinome do projeto e da infraestrutura, não o nome do agente.** O agente nasce
> sem nome pessoal (`chosen_name = null`). O sistema não alega consciência, sentimentos ou vida.

## Estado atual

**Fases 0–6 construídas.** Concluídas: 0, 1, 3, 4 e 6; implementadas com pendências de uso real:
2 (voz) e 5 (iniciativas). Avaliações em [docs/EVALUATION.md](docs/EVALUATION.md).

- Identidade mínima (UUID, nome `null`) e conversa via LLM substituível (qualquer endpoint
  compatível com OpenAI), com orçamento e custo registrados.
- Memória curada entre conversas, opt-in por usuário ([docs/MEMORY.md](docs/MEMORY.md)).
- Interface web com a bolha de estados e voz: fala com a voz escolhida pelo próprio agente e
  escuta pelo microfone ([docs/VOICE.md](docs/VOICE.md)). Falta o teste com microfone real e no
  iPhone.
- Curiosidade: detecta lacunas, pergunta o que é pessoal e pesquisa fatos públicos na Wikipédia
  citando fontes ([docs/CURIOSITY.md](docs/CURIOSITY.md)).
- Iniciativas: perguntas sem resposta podem virar metas que só rodam com aprovação, num worker
  separado ([docs/AUTONOMY.md](docs/AUTONOMY.md)).
- Adaptação: o jeito de responder se ajusta ao seu retorno de forma versionada e reversível
  ([docs/IDENTITY.md](docs/IDENTITY.md)).

Veja [docs/ROADMAP.md](docs/ROADMAP.md).

Para conversar, preencha as variáveis `VISION_LLM_*` do `.env` (veja `.env.example`). Sem todas
elas, inclusive os preços, a API responde 503 em vez de inventar uma resposta.

## Execução local

### Com Docker (caminho oficial)

```bash
cp .env.example .env        # edite VISION_SECRET_KEY e POSTGRES_PASSWORD
docker compose up --build
```

- API: http://127.0.0.1:8000 (`/health`, `/ready`, `/docs`)
- PostgreSQL fica acessível apenas em `127.0.0.1:5432`.

Criar o usuário inicial e executar o genesis (idempotente):

```bash
docker compose exec api python -m apps.api.cli create-user --email voce@exemplo.com
```

```bash
docker compose exec api python -m apps.api.cli genesis
```

### Sem Docker (desenvolvimento)

Requer Python 3.12+.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
VISION_DATABASE_URL=sqlite:///./dev.db .venv/bin/alembic upgrade head
VISION_DATABASE_URL=sqlite:///./dev.db .venv/bin/uvicorn apps.api.main:app --reload
```

SQLite serve só para desenvolvimento e testes unitários; o banco de referência é PostgreSQL.

### Interface web (desenvolvimento)

Requer Node.js 22+. Com a API rodando em `127.0.0.1:8000`:

```bash
npm --prefix apps/web install
npm --prefix apps/web run dev
```

Abra http://localhost:5173. A demonstração dos estados da bolha fica em
http://localhost:5173/?orb=demo.

### Worker (iniciativas aprovadas)

```bash
.venv/bin/python -m apps.worker.main
```

No Docker Compose ele sobe como serviço `worker`.

### Voz (opcional)

```bash
.venv/bin/pip install -e ".[tts,stt]"
```

Baixe os modelos para `models/tts/` (links e tamanhos em
[docs/research-log/2026-10-31-fase-2b-tts.md](docs/research-log/2026-10-31-fase-2b-tts.md)),
defina `VISION_TTS_APPROVED_VOICES` no `.env` e deixe o agente decidir:

```bash
.venv/bin/python -m apps.api.cli voice-deliberation
```

### Testes

```bash
.venv/bin/pytest                                   # unitários + API (SQLite em memória)
VISION_TEST_DATABASE_URL=postgresql+psycopg://... .venv/bin/pytest -m postgres
.venv/bin/ruff check .
```

## Documentação

- [Arquitetura](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Genesis](docs/GENESIS.md)
- [Nome autônomo](docs/AUTONOMOUS_NAMING.md)
- [Curiosidade](docs/CURIOSITY.md)
- [Seleção de modelos](docs/MODEL_SELECTION.md)
- [Custos e limites](docs/COSTS.md)
- [Decisões (ADRs)](docs/decisions/)
- [Diário de pesquisa](docs/research-log/)
