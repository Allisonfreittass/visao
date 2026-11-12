#!/bin/bash
# Prepara um Ubuntu 24.04 novo (Lightsail) para o Visão. Rodar uma vez, como ubuntu:
#   sudo bash bootstrap.sh "<chave pública do deploy>" <domínio>
# Faz: atualizações automáticas de segurança, firewall (22, 80, 443), 2 GB de swap, Docker do
# repositório oficial, usuário deploy (grupo docker, sem sudo, só a chave dada) e as pastas
# /opt/visao (do deploy) e /etc/visao (segredos: root, leitura do grupo deploy).
set -euo pipefail
deploy_key=${1:?informe a chave pública do usuário deploy}
domain=${2:?informe o domínio (ex.: 1-2-3-4.sslip.io)}
[ "$(id -u)" = 0 ] || { echo "Rode com sudo." >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl ufw unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
printf '%s\n' "$deploy_key" > /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys

install -d -m 755 -o deploy -g deploy /opt/visao /opt/visao/incoming /opt/visao/releases
touch /opt/visao/release.env && chown deploy:deploy /opt/visao/release.env
install -d -m 750 -o root -g deploy /etc/visao
[ -f /etc/visao/app.env ] || install -m 640 -o root -g deploy /dev/null /etc/visao/app.env
printf 'VISAO_DOMAIN=%s\n' "$domain" > /etc/visao/caddy.env
chown root:deploy /etc/visao/caddy.env && chmod 640 /etc/visao/caddy.env

echo "Pronto. Preencha /etc/visao/app.env (modelo: deploy/app.env.example) e rode o deploy."
