# Developer shortcuts; `npm run <target>` at the repository root calls the same targets.
# `make check` is what CI runs (lint + tests), minus the docker and Cloudflare jobs.

VENV ?= .venv
PY := $(VENV)/bin
WEB := apps/web

.PHONY: help setup test test-api test-web lint check db-test start

help:
	@echo "make setup    cria .venv, instala o pacote com [dev] e as dependências do web"
	@echo "make test     pytest + vitest do web"
	@echo "make lint     ruff check, ruff format --check e typecheck do web"
	@echo "make check    lint e test"
	@echo "make db-test  testes -m postgres num pgvector descartável (requer docker)"
	@echo "make start    API, worker e web juntos (scripts/dev.sh)"

$(PY)/python:
	python3 -m venv $(VENV)

setup: $(PY)/python
	$(PY)/pip install -e ".[dev]"
	npm ci --prefix $(WEB)

test: test-api test-web

test-api:
	$(PY)/pytest -q

test-web:
	npm --prefix $(WEB) test

lint:
	$(PY)/ruff check .
	$(PY)/ruff format --check .
	npm --prefix $(WEB) run typecheck

check: lint test

db-test:
	scripts/db-test.sh

start:
	scripts/dev.sh
