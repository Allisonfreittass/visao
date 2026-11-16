#!/bin/bash
# Instala (ou atualiza) o backup do banco no servidor (docs/BACKUP.md). Rodar como ubuntu:
#   scp deploy/backup.sh deploy/backup-install.sh ubuntu@<IP>:
#   ssh ubuntu@<IP> "sudo bash backup-install.sh age1..."   (a chave PÚBLICA de fechar)
# O script fica em /usr/local/sbin, de root: o deploy automático não o troca, porque ele roda
# como root e o usuário deploy não deve poder mudar o que o root executa.
set -euo pipefail
recipient=${1:?informe a chave pública age (age1...)}
case $recipient in age1*) ;; *) echo "Isso não é uma chave pública age." >&2; exit 1 ;; esac
[ "$(id -u)" = 0 ] || { echo "Rode com sudo." >&2; exit 1; }
cd "$(dirname "$0")"

command -v age >/dev/null || { apt-get update -q && apt-get install -yq age; }
install -m 700 -o root -g root backup.sh /usr/local/sbin/visao-backup

if [ -f /etc/visao/backup.env ]; then
  sed -i "s/^VISAO_BACKUP_AGE_RECIPIENT=.*/VISAO_BACKUP_AGE_RECIPIENT=$recipient/" /etc/visao/backup.env
else
  install -m 600 -o root -g root /dev/null /etc/visao/backup.env
  cat > /etc/visao/backup.env <<CONF
# Backup do banco (docs/BACKUP.md). Só root lê este arquivo.
VISAO_BACKUP_AGE_RECIPIENT=$recipient
# Cópia fora do servidor (opcional): um bucket R2 do Cloudflare e um token só dele.
VISAO_BACKUP_R2_BUCKET=
VISAO_BACKUP_R2_ENDPOINT=
VISAO_BACKUP_R2_ACCESS_KEY_ID=
VISAO_BACKUP_R2_SECRET_ACCESS_KEY=
CONF
fi
install -d -m 700 /var/backups/visao
install -d -m 755 /var/backups/visao/status

cat > /etc/systemd/system/visao-backup.service <<'UNIT'
[Unit]
Description=Backup do banco do Visão (docs/BACKUP.md)
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/visao-backup
UNIT

cat > /etc/systemd/system/visao-backup.timer <<'UNIT'
[Unit]
Description=Backup do banco do Visão toda madrugada

[Timer]
OnCalendar=*-*-* 03:30:00 America/Sao_Paulo
RandomizedDelaySec=10min
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now visao-backup.timer
echo "Backup instalado. Próximo: $(systemctl list-timers visao-backup.timer --no-legend | awk '{print $1, $2, $3}')"
