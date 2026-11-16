#!/bin/sh
# Backup do banco do Visão (docs/BACKUP.md, ADR-0019). Roda como root pelo timer
# visao-backup.timer, toda madrugada:
#   1. pg_dump do schema do Visão (o Supabase de VISION_DATABASE_URL), no formato custom;
#   2. confere a cópia (pg_restore --list e as tabelas que não podem faltar) e conta as linhas;
#   3. empacota a cópia e a contagem e criptografa com age, para a chave pública de
#      /etc/visao/backup.env (a chave de abrir fica só com o dono, fora do servidor);
#   4. guarda em /var/backups/visao: 14 dias, e o do dia 1 de cada mês por 6 meses;
#   5. se houver um bucket R2 configurado, manda uma cópia para lá;
#   6. escreve status/last.json, que a API e o worker leem (o resumo da manhã avisa se falhar).
# Nenhum segredo vai para a linha de comando: a URL do banco e as chaves do R2 passam por
# variáveis de ambiente para os containers.
set -eu
umask 077

# Os caminhos podem ser trocados por variáveis só para o teste local (scripts/backup-test.sh).
DIR=${VISAO_BACKUP_DIR:-/var/backups/visao}
STATUS_DIR=$DIR/status
APP_ENV=${VISAO_BACKUP_APP_ENV:-/etc/visao/app.env}
BACKUP_ENV=${VISAO_BACKUP_ENV:-/etc/visao/backup.env}
PG_IMAGE=postgres:17-alpine          # pg_dump precisa ser da mesma versão do servidor ou mais nova
RCLONE_IMAGE=rclone/rclone:1.68.2
NETWORK=${VISAO_BACKUP_NETWORK:-visao_default}  # a rede com IPv6 do compose (Supabase é só IPv6)
REQUIRED="users conversations messages memory_records"
KEEP_DAYS=14
KEEP_MONTHLY_DAYS=186

mkdir -p "$DIR" "$STATUS_DIR"
chmod 755 "$STATUS_DIR"  # só o status é lido pelos containers; as cópias ficam 600
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
step=config

status() {  # status <ok> <campos JSON extras>
  printf '{"ok": %s, "at": "%s", "step": "%s"%s}\n' "$1" "$started" "$step" "${2:-}" \
    > "$STATUS_DIR/last.json.tmp"
  chmod 644 "$STATUS_DIR/last.json.tmp"
  mv "$STATUS_DIR/last.json.tmp" "$STATUS_DIR/last.json"
}

work=$(mktemp -d)
trap 'rc=$?; rm -rf "$work"; if [ $rc -ne 0 ]; then status false; fi' EXIT

value() {  # value NOME ARQUIVO: o valor de NOME=..., sem aspas, sem ecoar
  grep -m1 "^$1=" "$2" 2>/dev/null | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' \
    -e "s/^'//" -e "s/'$//"
}

DBURL=$(value VISION_DATABASE_URL "$APP_ENV" | sed 's#^postgresql+[a-z0-9]*://#postgresql://#')
SCHEMA=$(value VISION_DATABASE_SCHEMA "$APP_ENV")
SCHEMA=${SCHEMA:-visao}
RECIPIENT=$(value VISAO_BACKUP_AGE_RECIPIENT "$BACKUP_ENV")
case $DBURL in postgresql://*) ;; *) echo "VISION_DATABASE_URL não é PostgreSQL" >&2; exit 1 ;; esac
case $RECIPIENT in age1*) ;; *) echo "falta VISAO_BACKUP_AGE_RECIPIENT em $BACKUP_ENV" >&2; exit 1 ;; esac
export DBURL

step=dump
docker run --rm --network "$NETWORK" -e DBURL "$PG_IMAGE" \
  sh -c 'pg_dump "$DBURL" --schema="$0" --format=custom --no-owner --no-privileges' "$SCHEMA" \
  > "$work/visao.dump"

step=verify
docker run --rm -i "$PG_IMAGE" pg_restore --list < "$work/visao.dump" > "$work/list"
tables=$(grep -c " TABLE DATA $SCHEMA " "$work/list" || true)
for table in $REQUIRED; do
  grep -q " TABLE DATA $SCHEMA $table " "$work/list" || {
    echo "a cópia não tem a tabela $table" >&2
    exit 1
  }
done

step=count
docker run --rm --network "$NETWORK" -e DBURL "$PG_IMAGE" sh -c 'psql "$DBURL" -AtF , -c "
  select table_name,
         (xpath(\$\$/row/c/text()\$\$, query_to_xml(format(\$\$select count(*) as c from %I.%I\$\$,
           table_schema, table_name), false, true, \$\$\$\$)))[1]::text::bigint
  from information_schema.tables
  where table_schema = \$\$$0\$\$ and table_type = \$\$BASE TABLE\$\$
  order by 1"' "$SCHEMA" > "$work/rows.csv"
rows=$(awk -F , '{s += $2} END {print s + 0}' "$work/rows.csv")
sha=$(sha256sum "$work/visao.dump" | cut -d' ' -f1)
printf 'sha256,%s\ntaken_at,%s\nschema,%s\n' "$sha" "$started" "$SCHEMA" > "$work/manifest.csv"

step=encrypt
name=visao-$(date -u +%Y%m%d-%H%M).tar.age
tar -C "$work" -cf - visao.dump rows.csv manifest.csv | age -r "$RECIPIENT" > "$DIR/$name.tmp"
mv "$DIR/$name.tmp" "$DIR/$name"
(cd "$DIR" && sha256sum "$name" > "$name.sha256")
bytes=$(stat -c %s "$DIR/$name")

step=retention
find "$DIR" -maxdepth 1 -name 'visao-*.tar.age*' -mtime +"$KEEP_DAYS" \
  ! -name 'visao-??????01-*' -delete
find "$DIR" -maxdepth 1 -name 'visao-*.tar.age*' -mtime +"$KEEP_MONTHLY_DAYS" -delete

step=offsite
offsite=none
BUCKET=$(value VISAO_BACKUP_R2_BUCKET "$BACKUP_ENV")
if [ -n "$BUCKET" ]; then
  RCLONE_CONFIG_R2_TYPE=s3
  RCLONE_CONFIG_R2_PROVIDER=Cloudflare
  RCLONE_CONFIG_R2_ENDPOINT=$(value VISAO_BACKUP_R2_ENDPOINT "$BACKUP_ENV")
  RCLONE_CONFIG_R2_ACCESS_KEY_ID=$(value VISAO_BACKUP_R2_ACCESS_KEY_ID "$BACKUP_ENV")
  RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=$(value VISAO_BACKUP_R2_SECRET_ACCESS_KEY "$BACKUP_ENV")
  RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
  export RCLONE_CONFIG_R2_TYPE RCLONE_CONFIG_R2_PROVIDER RCLONE_CONFIG_R2_ENDPOINT \
    RCLONE_CONFIG_R2_ACCESS_KEY_ID RCLONE_CONFIG_R2_SECRET_ACCESS_KEY RCLONE_CONFIG_R2_NO_CHECK_BUCKET
  rclone() {
    docker run --rm -v "$DIR:/data:ro" -e RCLONE_CONFIG_R2_TYPE -e RCLONE_CONFIG_R2_PROVIDER \
      -e RCLONE_CONFIG_R2_ENDPOINT -e RCLONE_CONFIG_R2_ACCESS_KEY_ID \
      -e RCLONE_CONFIG_R2_SECRET_ACCESS_KEY -e RCLONE_CONFIG_R2_NO_CHECK_BUCKET \
      "$RCLONE_IMAGE" "$@"
  }
  if rclone copy "/data/$name" "r2:$BUCKET/" --quiet \
    && rclone copy "/data/$name.sha256" "r2:$BUCKET/" --quiet; then
    offsite=r2
    rclone delete "r2:$BUCKET/" --min-age 35d --include 'visao-*' --quiet || true
  else
    offsite=failed
  fi
fi

step=done
status true ", \"file\": \"$name\", \"bytes\": $bytes, \"tables\": $tables, \"rows\": $rows, \"offsite\": \"$offsite\""
cp "$STATUS_DIR/last.json" "$STATUS_DIR/last_ok.json"
chmod 644 "$STATUS_DIR/last_ok.json"  # umask 077: os containers não são root
echo "backup ok: $name ($bytes bytes, $tables tabelas, $rows linhas, cópia fora: $offsite)"
