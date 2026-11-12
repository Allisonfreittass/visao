#!/usr/bin/env bash
# Starts API, worker and web together for local use; Ctrl+C stops all three.
# Usage: npm start   (or: scripts/dev.sh). Written for macOS's bash 3.2; also runs on Linux.
set -eo pipefail
cd "$(dirname "$0")/.."

# lsof ships with macOS; minimal Linux installs may only have ss, or neither (then bash's
# /dev/tcp: a successful connection means something is listening).
port_in_use() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  elif command -v ss >/dev/null 2>&1; then
    ss -Hltn "sport = :$1" 2>/dev/null | grep -q .
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
  fi
}

for port in 8000 5173; do
  if port_in_use "$port"; then
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
# Line-buffered prefixing: BSD sed spells it -l, GNU sed -u (where -l means line length).
if sed --version >/dev/null 2>&1; then line_buffered=-u; else line_buffered=-l; fi
run() {
  local name=$1
  shift
  "$@" > >(sed "$line_buffered" "s/^/[$name] /") 2>&1 &
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
