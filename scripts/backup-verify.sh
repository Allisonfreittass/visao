#!/usr/bin/env bash
# Confere um backup do banco de verdade (docs/BACKUP.md): baixa o mais recente do servidor (ou usa
# o arquivo dado), confere o sha256, abre com a SUA chave (que nunca vai ao servidor), restaura
# num PostgreSQL temporário e compara as linhas de cada tabela com as contadas na hora do backup.
# Uso: make backup-verify            (o mais recente do servidor)
#      scripts/backup-verify.sh arquivo.tar.age
set -euo pipefail
cd "$(dirname "$0")/.."

key=${VISAO_BACKUP_KEY:-$HOME/.config/visao/backup-age.key}
remote_dir=/var/backups/visao
pg_image=postgres:17-alpine
age_image=visao-age:local
[ -f "$key" ] || { echo "Falta a chave de abrir em $key (docs/BACKUP.md)." >&2; exit 1; }

work=$(mktemp -d)
name="visao-backup-verify-$$"
cleanup() { docker stop "$name" >/dev/null 2>&1 || true; rm -rf "$work"; }
trap cleanup EXIT

docker image inspect "$age_image" >/dev/null 2>&1 \
  || printf 'FROM alpine:3.20\nRUN apk add --no-cache age\n' | docker build -q -t "$age_image" - >/dev/null

file=${1:-}
if [ -z "$file" ]; then
  host=$(grep -m1 '^VPS_HOST=' "$HOME/.config/visao/servidor.env" | cut -d= -f2 | awk '{print $1}')
  ssh_cmd=(ssh -i "$HOME/.config/visao/visao-admin" "ubuntu@$host")
  latest=$("${ssh_cmd[@]}" "sudo ls -1t $remote_dir" | grep -m1 '^visao-.*\.tar\.age$')
  "${ssh_cmd[@]}" "sudo cat $remote_dir/$latest" > "$work/$latest"
  "${ssh_cmd[@]}" "sudo cat $remote_dir/$latest.sha256" > "$work/$latest.sha256"
  (cd "$work" && sha256sum --quiet -c "$latest.sha256")
  file=$work/$latest
fi
echo "Conferindo $(basename "$file")"

docker run --rm -i -v "$key:/key:ro" "$age_image" age -d -i /key < "$file" | tar -x -C "$work"
schema=$(grep '^schema,' "$work/manifest.csv" | cut -d, -f2)
(cd "$work" && [ "$(sha256sum visao.dump | cut -d' ' -f1)" = "$(grep '^sha256,' manifest.csv | cut -d, -f2)" ]) \
  || { echo "A cópia aberta não bate com o sha256 gravado." >&2; exit 1; }

docker run --detach --rm --name "$name" -e POSTGRES_PASSWORD=verify "$pg_image" >/dev/null
for _ in $(seq 60); do
  docker exec "$name" pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1 && break
  sleep 1
done
# The policies name the app's own role (visao_app in production): it must exist to restore them.
docker exec -i "$name" pg_restore -f - < "$work/visao.dump" \
  | sed -n 's/^CREATE POLICY .* TO \([a-z_0-9]*\) .*/\1/p' | sort -u | while read -r role; do
    exists=$(docker exec "$name" psql -h 127.0.0.1 -U postgres -Atc \
      "select 1 from pg_roles where rolname = '$role'")
    [ -n "$exists" ] || docker exec "$name" psql -h 127.0.0.1 -U postgres -qc \
      "create role \"$role\" nologin" >/dev/null
  done
docker exec -i "$name" pg_restore -h 127.0.0.1 -U postgres -d postgres --no-owner --exit-on-error \
  < "$work/visao.dump"

missing=0
while IFS=, read -r table expected; do
  got=$(docker exec "$name" psql -h 127.0.0.1 -U postgres -At -c "select count(*) from \"$schema\".\"$table\"")
  if [ "$expected" -gt 0 ] && [ "$got" -eq 0 ]; then
    echo "  $table: vazia na restauração, eram $expected" >&2
    missing=1
  elif [ "$got" != "$expected" ]; then
    echo "  $table: $got restauradas, $expected contadas logo depois da cópia"
  fi
done < "$work/rows.csv"
[ "$missing" -eq 0 ] || { echo "Backup NÃO confere." >&2; exit 1; }
tables=$(wc -l < "$work/rows.csv")
rows=$(awk -F , '{s += $2} END {print s + 0}' "$work/rows.csv")
echo "Backup ok: restaurado inteiro, $tables tabelas, ~$rows linhas, tirado em $(grep '^taken_at,' "$work/manifest.csv" | cut -d, -f2)."
