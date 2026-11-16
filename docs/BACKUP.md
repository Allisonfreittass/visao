# Backup do banco

Toda madrugada (03:30), o servidor tira uma cópia do schema `visao` do Supabase, confere que ela
abre, criptografa e guarda ([ADR-0019](decisions/0019-backup-do-banco.md)). Se algo falhar, o
resumo da manhã avisa.

## Onde estão

| O quê | Onde |
|---|---|
| Cópias criptografadas | servidor, `/var/backups/visao/visao-AAAAMMDD-HHMM.tar.age` (+ `.sha256`): 14 dias, e o dia 1 de cada mês por 6 meses |
| Cópia fora do servidor (opcional) | bucket R2 configurado em `/etc/visao/backup.env`, 35 dias |
| Status | `/var/backups/visao/status/last.json` e `last_ok.json` |
| Chave pública (fechar) | `/etc/visao/backup.env`, no servidor |
| **Chave privada (abrir)** | `~/.config/visao/backup-age.key`, só no seu computador. **Guarde uma cópia num gerenciador de senhas: sem ela, nenhum backup abre.** |

Dentro de cada arquivo, depois de aberto:
- `visao.dump`: o `pg_dump` em formato custom;
- `rows.csv`: as linhas de cada tabela na hora da cópia;
- `manifest.csv`: o sha256 do dump, a hora e o schema.

## Conferir

```bash
make backup-verify
```

O comando baixa o backup mais recente, confere o sha256, abre com a sua chave, restaura num
Postgres temporário e compara as tabelas. Termina com "Backup ok: restaurado inteiro…".

```bash
make backup-test
```

Faz o mesmo caminho inteiro com um banco e uma chave de teste, sem tocar em produção.

## Rodar agora, ver o timer, ver o log

```bash
ssh -i ~/.config/visao/visao-admin ubuntu@<IP> "sudo systemctl start visao-backup && sudo cat /var/backups/visao/status/last.json"
```

```bash
ssh -i ~/.config/visao/visao-admin ubuntu@<IP> "systemctl list-timers visao-backup.timer; sudo journalctl -u visao-backup -n 20"
```

## Ligar a cópia fora do servidor (R2)

1. No Cloudflare, em R2, crie um bucket (ex.: `visao-backup`) e um token de API com permissão
   **Object Read & Write só nesse bucket**.
2. No servidor, `sudo nano /etc/visao/backup.env` e preencha `VISAO_BACKUP_R2_BUCKET`,
   `VISAO_BACKUP_R2_ENDPOINT` (`https://<account-id>.r2.cloudflarestorage.com`),
   `VISAO_BACKUP_R2_ACCESS_KEY_ID` e `VISAO_BACKUP_R2_SECRET_ACCESS_KEY`.
3. Rode o backup agora (comando acima). O status deve dizer `"offsite": "r2"`.

## Restaurar em produção (só se precisar)

Nunca é automático. Com o app parado (`docker compose stop api worker` em `/opt/visao`):
1. abra o arquivo com `age -d -i ~/.config/visao/backup-age.key arquivo.tar.age | tar -x`;
2. restaure num schema novo primeiro (`pg_restore --no-owner -d <url>` depois de renomear o schema
   no dump, ou num banco temporário) e confira;
3. só então troque o schema `visao` pelo restaurado. Depois, suba o app.

Antes de restaurar, tire um backup do estado atual: `sudo systemctl start visao-backup`.

## Instalar (ou atualizar o script)

```bash
scp -i ~/.config/visao/visao-admin deploy/backup.sh deploy/backup-install.sh ubuntu@<IP>:
```

```bash
ssh -i ~/.config/visao/visao-admin ubuntu@<IP> "sudo bash backup-install.sh $(grep -m1 '^# public key:' ~/.config/visao/backup-age.key | cut -d' ' -f4)"
```

O script fica em `/usr/local/sbin/visao-backup`, de root: o deploy automático não o troca.
