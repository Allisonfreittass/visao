#!/usr/bin/env bash
# Runs the PostgreSQL-only tests (-m postgres) against a throwaway pgvector container bound to
# a free local port, so it never touches a real database or a port already in use.
# Usage: make db-test   (or: scripts/db-test.sh [extra pytest args])
set -euo pipefail
cd "$(dirname "$0")/.."

image=pgvector/pgvector:pg16  # same image as docker-compose.yml and CI
name="visao-db-test-$$"
port=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')

docker run --detach --rm --name "$name" \
  -e POSTGRES_DB=vision_test -e POSTGRES_USER=vision -e POSTGRES_PASSWORD=vision \
  -p "127.0.0.1:$port:5432" "$image" >/dev/null
trap 'docker stop "$name" >/dev/null 2>&1 || true' EXIT

# Over TCP, so the temporary server the image runs during initialisation does not count.
ready=""
for _ in $(seq 60); do
  if docker exec "$name" pg_isready -h 127.0.0.1 -U vision -d vision_test >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ -z "$ready" ]; then
  echo "O PostgreSQL de teste não ficou pronto em 60 s." >&2
  exit 1
fi

VISION_TEST_DATABASE_URL="postgresql+psycopg://vision:vision@127.0.0.1:$port/vision_test" \
  .venv/bin/pytest -m postgres "$@"
