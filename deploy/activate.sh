#!/bin/sh
# Ativa uma release já enviada ao servidor: carrega a imagem e o web dessa SHA, aponta
# /opt/visao para ela e recria os containers. Rodado pelo usuário deploy (sem sudo) a cada
# deploy, e de novo com a SHA anterior para voltar atrás. Uso: sh activate.sh <sha>
set -eu
sha=${1:?informe a SHA}
case $sha in *[!0-9a-f]*) echo "SHA inválida: $sha" >&2; exit 2 ;; esac
cd /opt/visao
incoming=/opt/visao/incoming
release=/opt/visao/releases/$sha

if [ -f "$incoming/visao-$sha.tar.gz" ]; then
  gunzip -c "$incoming/visao-$sha.tar.gz" | docker load >/dev/null
  rm -f "$incoming/visao-$sha.tar.gz"
fi
if [ -f "$incoming/web-$sha.tar.gz" ]; then
  mkdir -p "$release/web"
  tar -xzf "$incoming/web-$sha.tar.gz" -C "$release/web"
  rm -f "$incoming/web-$sha.tar.gz"
fi
for file in docker-compose.yml Caddyfile activate.sh; do
  if [ -f "$incoming/$file" ]; then mv "$incoming/$file" "/opt/visao/$file"; fi
done

docker image inspect "visao:$sha" >/dev/null 2>&1 || { echo "Imagem visao:$sha não está no servidor" >&2; exit 1; }
[ -d "$release/web" ] || { echo "Web de $sha não está no servidor" >&2; exit 1; }

docker tag "visao:$sha" visao:current
ln -sfn "$sha/web" /opt/visao/releases/current
printf 'VISION_BUILD_SHA=%s\n' "$sha" > /opt/visao/release.env
docker compose up -d --remove-orphans
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true

# Guarda as 5 releases mais recentes (para voltar atrás) e apaga o resto.
ls -1t /opt/visao/releases | grep -v '^current$' | tail -n +6 | while read -r old; do
  [ "$old" = "$sha" ] && continue
  rm -rf "/opt/visao/releases/$old"
  docker image rm "visao:$old" >/dev/null 2>&1 || true
done
echo "Release ativa: $sha"
