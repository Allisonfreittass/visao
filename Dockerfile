FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 1000 vision

COPY pyproject.toml ./
COPY apps ./apps
COPY core ./core
COPY integrations ./integrations
COPY infrastructure ./infrastructure
RUN pip install -c infrastructure/deployment/constraints.txt .

# Read by the agent itself (docs/SELF_KNOWLEDGE.md); the source above is read from /app too.
COPY README.md ./
COPY docs/*.md ./docs/
COPY docs/decisions ./docs/decisions
COPY arm ./arm

COPY alembic.ini ./
COPY migrations ./migrations

USER vision
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["sh", "-c", "alembic upgrade head && uvicorn apps.api.main:app --host 0.0.0.0 --port 8000"]
