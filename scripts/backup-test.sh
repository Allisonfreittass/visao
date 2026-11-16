#!/usr/bin/env bash
# Testa o backup de ponta a ponta sem tocar no banco de verdade (docs/BACKUP.md): um PostgreSQL
# temporário com as migrações e a gênese, deploy/backup.sh com caminhos de teste e uma chave de
# teste, e scripts/backup-verify.sh restaurando a cópia gerada.
# Uso: make backup-test
set -euo pipefail
cd "$(dirname "$0")/.."

age_image=visao-age:local
network="visao-backup-test-$$"
db="visao-backup-db-$$"
work=$(mktemp -d)
cleanup() {
  docker stop "$db" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

docker image inspect "$age_image" >/dev/null 2>&1 \
  || printf 'FROM alpine:3.20\nRUN apk add --no-cache age\n' | docker build -q -t "$age_image" - >/dev/null
docker network create "$network" >/dev/null
port=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
docker run --detach --rm --name "$db" --network "$network" -e POSTGRES_PASSWORD=teste \
  -p "127.0.0.1:$port:5432" postgres:17-alpine >/dev/null
for _ in $(seq 60); do
  docker exec "$db" pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1 && break
  sleep 1
done

docker exec "$db" psql -h 127.0.0.1 -U postgres -qc 'create schema visao' >/dev/null
export VISION_DATABASE_URL="postgresql+psycopg://postgres:teste@127.0.0.1:$port/postgres"
export VISION_DATABASE_SCHEMA=visao
.venv/bin/alembic upgrade head >/dev/null
.venv/bin/python -m apps.api.cli genesis >/dev/null

docker run --rm "$age_image" age-keygen > "$work/key" 2>/dev/null
recipient=$(grep -m1 '^# public key: ' "$work/key" | cut -d' ' -f4)
printf 'VISION_DATABASE_URL=postgresql+psycopg://postgres:teste@%s:5432/postgres\nVISION_DATABASE_SCHEMA=visao\n' \
  "$db" > "$work/app.env"
printf 'VISAO_BACKUP_AGE_RECIPIENT=%s\n' "$recipient" > "$work/backup.env"
mkdir -p "$work/bin"
printf '#!/bin/sh\nexec docker run --rm -i %s age "$@"\n' "$age_image" > "$work/bin/age"
chmod +x "$work/bin/age"

PATH="$work/bin:$PATH" VISAO_BACKUP_DIR="$work/backups" VISAO_BACKUP_APP_ENV="$work/app.env" \
  VISAO_BACKUP_ENV="$work/backup.env" VISAO_BACKUP_NETWORK="$network" sh deploy/backup.sh
grep -q '"ok": true' "$work/backups/status/last.json"
file=$(ls -1 "$work"/backups/visao-*.tar.age | head -1)
VISAO_BACKUP_KEY="$work/key" scripts/backup-verify.sh "$file"
echo "Teste do backup ok."
