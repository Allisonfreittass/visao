# Visão no Lightsail

Desde 2026-11-12 o Visão roda num servidor só dele (AWS Lightsail, Ubuntu 24.04), com o worker
ligado 24 h: é isso que deixa ele pensar, estudar e puxar conversa sem o Mac. Saiu do Cloudflare
porque lá o Container dormia depois de 2 minutos, o cron tinha sido tirado e o plano Workers Paid
deixou de existir na conta ([CLOUDFLARE.md](CLOUDFLARE.md) fica como histórico).

| Peça | Onde |
|---|---|
| Servidor | Lightsail `visao`, IP fixo, Ubuntu 24.04 (atualizações automáticas, `ufw` só 22/80/443, 2 GB de swap) |
| Endereço | `https://<ip-com-traços>.sslip.io` (o nome aponta para o IP; o Caddy tira o certificado) |
| API e worker | containers `api` e `worker` (imagem `visao:<sha>`, ativa como `visao:current`) |
| HTTPS e web | container `caddy`: certificado automático, o build do web e `/api/*` para a API |
| Arquivos do deploy | `/opt/visao` (`docker-compose.yml`, `Caddyfile`, `activate.sh`, `releases/<sha>/web`) |
| Segredos | `/etc/visao/app.env` (dono root, leitura do grupo `deploy`), modelo em [`deploy/app.env.example`](../deploy/app.env.example) |
| Banco | o PostgreSQL de `VISION_DATABASE_URL` (o Supabase de sempre, schema `visao`) |

## Acesso

- **Manutenção:** `ssh -i ~/.config/visao/visao-admin ubuntu@<IP>` (tem `sudo`).
- **Deploy (GitHub Actions):** usuário `deploy`, chave `~/.config/visao/visao-deploy`, grupo
  `docker`, **sem `sudo`**. A chave privada fica só no segredo `VPS_SSH_KEY` do Environment
  `production`.

As duas chaves, as chaves VAPID e um LEIA-ME ficam em `~/.config/visao/` (permissão 700). Para
levar ao Mac, veja o LEIA-ME de lá.

## Primeira vez

1. Crie a instância no console do Lightsail (São Paulo, Ubuntu 24.04, 2 GB). Em *Advanced
   settings › Launch script*, acrescente a chave pública `visao-admin.pub` ao
   `/home/ubuntu/.ssh/authorized_keys`. Depois anexe um IP estático e, em Networking, libere
   HTTPS (443); 22 e 80 já vêm abertas.
2. Prepare o servidor:
   ```bash
   scp -i ~/.config/visao/visao-admin deploy/bootstrap.sh ubuntu@<IP>:
   ssh -i ~/.config/visao/visao-admin ubuntu@<IP> \
     "sudo bash bootstrap.sh '$(cat ~/.config/visao/visao-deploy.pub)' <ip-com-traços>.sslip.io"
   ```
3. Preencha os segredos: `sudo nano /etc/visao/app.env` (modelo em `deploy/app.env.example`).
4. No GitHub: variável `VISAO_PUBLIC_URL=https://<ip-com-traços>.sslip.io` e, no Environment
   `production`, os segredos `VPS_HOST` (o IP), `VPS_SSH_KEY` (`visao-deploy`) e
   `VPS_KNOWN_HOSTS` (`ssh-keyscan -t ed25519 <IP>`).
5. Actions › **CD** › *Run workflow*. Pronto quando o release mostrar a SHA no ar.

## Deploy automático

Todo push na `main` que passa no CI vai para o servidor pelo workflow `CD`
([`.github/workflows/cd.yml`](../.github/workflows/cd.yml)): build do web, imagem Docker, envio
por SSH e [`deploy/activate.sh`](../deploy/activate.sh), que troca a release. O controle
([`infrastructure/deployment/release.py`](../infrastructure/deployment/release.py)) só aceita a
versão quando `/api/release` mostra a SHA nova, `/api/ready` responde com o banco e a página abre;
senão ativa de novo a release que estava no ar. As migrações rodam quando a API sobe, então toda
migração precisa funcionar com o código anterior (acrescentar é seguro; apagar ou renomear, em
dois deploys).

Sem a variável `VISAO_PUBLIC_URL` o CD não roda: nada falha antes de o servidor existir.

## Dia a dia

```bash
ssh -i ~/.config/visao/visao-admin ubuntu@<IP>
cd /opt/visao
docker compose ps                         # api, worker e caddy
docker compose logs -f --tail=100 worker  # o que a mente está fazendo
docker stats --no-stream                  # memória e CPU
```

Voltar para uma versão anterior à mão (as 5 últimas ficam no servidor):

```bash
ls /opt/visao/releases
sh /opt/visao/activate.sh <sha>
```

Mudou um segredo? `sudo nano /etc/visao/app.env && cd /opt/visao && docker compose up -d`.

## O Mac depois da mudança

O worker do servidor é o único que pensa. `npm start` com o banco compartilhado no `.env` sobe só
API e web locais; `VISAO_LOCAL_WORKER=1 npm start` força um worker local, para quando o servidor
estiver parado. Dois workers no mesmo banco pensariam e falariam em dobro.

## Custos

Lightsail de 2 GB: US$ 12/mês, com IP, 60 GB de disco e 1,5 TB de tráfego (São Paulo). Os créditos da conta
cobrem até 22/04/2027, quando acaba o período do plano gratuito: para não cair, mude a conta para
o plano pago antes disso.
