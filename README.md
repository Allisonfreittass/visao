# VISÃO

Pesquisa experimental pessoal sobre arquitetura cognitiva persistente: memória autobiográfica,
curadoria de memória, busca orientada por incerteza, reflexão e metas persistentes em torno de
um LLM substituível.

> **VISÃO é o codinome do projeto e da infraestrutura, não o nome do agente.** O agente nasce
> sem nome pessoal (`chosen_name = null`). O sistema não alega consciência, sentimentos ou vida.

## Estado atual

**Fase 0: Fundação.** Veja [docs/ROADMAP.md](docs/ROADMAP.md) para o que existe e o que falta.
Nada de cognição (memória, curiosidade, voz, genesis) foi implementado ainda.

## Execução local

### Com Docker (caminho oficial)

```bash
cp .env.example .env        # edite VISION_SECRET_KEY e POSTGRES_PASSWORD
docker compose up --build
```

- API: http://127.0.0.1:8000 (`/health`, `/ready`, `/docs`)
- PostgreSQL fica acessível apenas em `127.0.0.1:5432`.

Criar o usuário inicial:

```bash
docker compose exec api python -m apps.api.cli create-user --email voce@exemplo.com
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
