# ADR-0001: Monólito modular em FastAPI + PostgreSQL

- Data: 2026-10-30
- Estado: aceita

## Contexto

Projeto pessoal de pesquisa, uma pessoa, infraestrutura pequena (Lightsail ~US$ 12/mês).
Precisa de estado persistente forte (memórias, identidade, auditoria), API HTTP/streaming,
jobs agendados e, mais tarde, voz em tempo real.

## Decisão

- Python 3.12 + FastAPI, um único processo de API e (a partir da Fase 1/5) um worker.
- PostgreSQL 16 como fonte única de verdade; imagem `pgvector/pgvector` para habilitar vetores
  quando a recuperação semântica for necessária (extensão ainda não criada na Fase 0).
- SQLAlchemy 2 (ORM tipado) + Alembic para migrações; toda migração com `downgrade`.
- Tipos portáveis (`Uuid`, `JSON`, `DateTime(timezone=True)`) para os testes unitários
  rodarem em SQLite; os testes marcados `postgres` rodam contra PostgreSQL real no CI.
- Layout de diretórios conforme seção 21 do master prompt, com pacotes Python na raiz
  (`apps`, `core`, `integrations`, `infrastructure`).
- Docker Compose para execução local e na instância; sem Kubernetes.
- Autenticação própria simples (Argon2id + JWT) para single-user, com modelo de `users` pronto
  para multiusuário.

## Alternativas consideradas

- **Microsserviços**: complexidade operacional sem benefício para uma pessoa.
- **Django**: admin útil, mas async e streaming são mais naturais no FastAPI.
- **SQLite em produção**: simples, mas fraco para worker concorrente e sem pgvector.
- **Redis/fila dedicada**: adiado; PostgreSQL (`SELECT ... FOR UPDATE SKIP LOCKED`) basta para
  jobs no volume previsto. Reavaliar com medição.

## Consequências

- Testes unitários rápidos sem dependências externas; risco de divergência SQLite/Postgres
  mitigado pela suíte `postgres` no CI.
- Nomes de pacotes genéricos na raiz (`core`, `apps`) exigem rodar a partir da raiz do repo ou
  instalar o projeto (`pip install -e .`).
