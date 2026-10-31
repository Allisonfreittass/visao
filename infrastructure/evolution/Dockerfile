FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && useradd --create-home --uid 1000 tester
WORKDIR /app
COPY pyproject.toml ./
COPY infrastructure/deployment/constraints.txt /tmp/constraints.txt
COPY apps ./apps
COPY core ./core
COPY integrations ./integrations
COPY infrastructure ./infrastructure
RUN pip install -c /tmp/constraints.txt '.[dev]'
RUN npm --prefix apps/web ci --ignore-scripts
COPY tests ./tests
COPY experiments ./experiments
COPY migrations ./migrations
COPY alembic.ini ./
RUN chown -R tester:tester /app
USER tester
ENV VISION_ENV_FILE=/dev/null VISION_ENVIRONMENT=test PYTHONDONTWRITEBYTECODE=1
CMD ["sh", "-c", "ruff check . && ruff format --check . && pytest -q -p no:cacheprovider && npm --prefix apps/web test && npm --prefix apps/web run build"]
