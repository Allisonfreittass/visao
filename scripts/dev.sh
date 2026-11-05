#!/usr/bin/env bash
# Starts API, worker and web together for local use; Ctrl+C stops all three.
# Usage: npm start   (or: scripts/dev.sh). Written for macOS's bash 3.2.
set -eo pipefail
cd "$(dirname "$0")/.."

for port in 8000 5173; do
  if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Porta $port já está em uso. Feche o processo que a usa e rode de novo." >&2
    exit 1
  fi
done

# Migrations change the database in place: automatic only for the local SQLite file. A shared
# database is migrated by the deploy, never by someone starting the app on a laptop.
if grep -Eq '^VISION_DATABASE_URL=postgres' .env 2>/dev/null; then
  head=$(.venv/bin/alembic heads 2>/dev/null | awk 'NR==1{print $1}')
  current=$(.venv/bin/alembic current 2>/dev/null | awk 'NR==1{print $1}')
  if [ -z "$current" ]; then
    echo "Não consegui ler o banco compartilhado: confira VISION_DATABASE_URL no .env." >&2
    exit 1
  fi
  if [ "$current" != "$head" ]; then
    echo "Banco compartilhado em $current, código em $head: publique antes de subir." >&2
    exit 1
  fi
else
  .venv/bin/alembic upgrade head
fi

pids=""
kill_tree() {
  local child
  for child in $(pgrep -P "$1"); do
    kill_tree "$child"
  done
  kill -TERM "$1" 2>/dev/null || true
}
stop() {
  trap - INT TERM EXIT
  for pid in $pids; do
    kill_tree "$pid"
  done
  wait 2>/dev/null || true
}
trap stop INT TERM EXIT

# Each process's output is prefixed with its name; $! is the process itself, not the prefixer.
run() {
  local name=$1
  shift
  "$@" > >(sed -l "s/^/[$name] /") 2>&1 &
  pids="$pids $!"
}

run api .venv/bin/uvicorn apps.api.main:app --port 8000 --reload
run worker .venv/bin/python -m apps.worker.main
run web npm --prefix apps/web run dev

echo "VISÃO: http://localhost:5173  (Ctrl+C para parar tudo)"
# Stop everything as soon as any one of them exits.
while true; do
  for pid in $pids; do
    kill -0 "$pid" 2>/dev/null || exit 1
  done
  sleep 1
done
