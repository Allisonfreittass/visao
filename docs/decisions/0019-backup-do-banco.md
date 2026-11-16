# ADR-0019: Backup do banco, criptografado, com restauração conferida

- Data: 2026-11-16
- Estado: aceita

## Contexto

As memórias, o temperamento, as conversas e os painéis só existiam no Supabase (schema `visao`,
Postgres 17, ~7 MB em 16/11/2026), sem nenhuma cópia nossa. Um erro, um projeto pausado ou a
mudança de servidor em 2027 podiam levar tudo. [GENESIS.md](../GENESIS.md) já exigia "backup
verificado (dump + checksum)" antes de qualquer reset, e ele não existia.

## Decisão

- **Toda madrugada, às 03:30 de São Paulo**, um timer do systemd no servidor roda
  `/usr/local/sbin/visao-backup` ([`deploy/backup.sh`](../../deploy/backup.sh)):
  - `pg_dump` só do schema `visao`, em formato custom, por um container `postgres:17-alpine`;
  - **conferência antes de guardar:** `pg_restore --list` precisa abrir a cópia e achar
    `users`, `conversations`, `messages` e `memory_records`; senão nada é gravado e o status
    diz em que etapa falhou;
  - contagem das linhas de cada tabela e sha256 da cópia, num manifesto que vai junto.
- **Criptografia com `age`.** O servidor só tem a chave pública (`/etc/visao/backup.env`). A
  chave de abrir fica com o dono, em `~/.config/visao/backup-age.key`. Quem pegar um arquivo do
  servidor ou do bucket não lê nada. **Perder a chave é perder os backups**, então guarde uma
  cópia dela fora do computador (num gerenciador de senhas).
- **Onde fica:**
  - **no disco do servidor**, em `/var/backups/visao`: os últimos 14 dias e o do dia 1 de cada
    mês por 6 meses. Isso protege contra perder o Supabase;
  - **opcionalmente num bucket R2 do Cloudflare** (até 10 GB grátis), por `rclone`, com 35 dias.
    Isso protege contra perder o servidor. Fica desligado até existir um bucket e um token.
- **Restauração conferida:** `make backup-verify`, no computador do dono:
  - baixa o backup mais recente e confere o sha256;
  - abre com a chave;
  - restaura num Postgres temporário;
  - compara as linhas de cada tabela com o manifesto.

  `make backup-test` faz o caminho inteiro com um banco e uma chave de teste, sem tocar em
  produção.
- **Aviso no resumo da manhã.** O backup escreve `status/last.json` e `status/last_ok.json`, que a
  API e o worker leem montados só para leitura (`VISION_BACKUP_STATUS_DIR`). O resumo da manhã
  (ADR-0017) avisa primeiro se:
  - o backup falhou;
  - o último backup bom tem mais de 36 h;
  - nunca rodou;
  - a cópia fora do servidor falhou.
- **O script é de root e não muda com o deploy.** Ele roda como root, e o usuário `deploy` não
  deve poder trocar o que o root executa. Para atualizar, rode `deploy/backup-install.sh` de novo.

## Fora desta decisão

- Backup contínuo (PITR): o plano grátis do Supabase não tem, e um por dia basta para o tamanho e
  o uso de hoje.
- Restauração em produção: é manual e documentada em [BACKUP.md](../BACKUP.md). Nunca é
  automática.
