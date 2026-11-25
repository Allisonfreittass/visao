# O app de Mac

> Etapa 7 de [research/execucao_local.md](research/execucao_local.md), em 2026-11-25. Decisão em
> [ADR-0027](decisions/0027-app-de-mac.md).

O Visão num app: um ícone no Dock, uma janela, nada de terminal. O app leva o servidor dentro
(Python congelado pelo PyInstaller) e não precisa de Python, Node nem Docker no Mac.

## Pegar o app

O CI monta o app num Mac com Apple Silicon a cada PR que mexe nele (`.github/workflows/desktop.yml`)
e também quando você roda o workflow à mão (Actions > desktop > Run workflow). O app sai como
artefato da execução, `Visao-mac` (um zip, guardado por 30 dias).

```bash
gh run download --repo Allisonfreittass/visao --name Visao-mac
unzip Visao-mac.zip && mv Visão.app /Applications/
xattr -dr com.apple.quarantine "/Applications/Visão.app"
```

O último comando é por causa da assinatura: o app não é assinado por uma conta paga da Apple, e o
macOS bloqueia na primeira abertura o que veio da internet sem ela. No lugar dele, dá para abrir
com botão direito > Abrir e confirmar. Só Apple Silicon por enquanto.

Para montar no seu próprio Mac (precisa de uv, Node 22 e Rust):

```bash
bash desktop/construir.sh       # sai em desktop/app/Visao-mac.zip
```

## Primeira abertura

1. O app mostra "Abrindo o Visão…" enquanto o servidor prepara o banco (alguns segundos na
   primeira vez).
2. Aparece a tela de primeiro uso: e-mail, senha (12 caracteres ou mais) e a senha de novo. Ela
   cria a sua conta e a identidade dele, e você já entra.
3. Falta o modelo: preencha o bloco `VISION_LLM_*` em `~/.visao/.env`
   ([MODEL_SELECTION.md](MODEL_SELECTION.md)), feche e abra o app de novo.

A tela de primeiro uso só aparece no seu Mac (pedido de 127.0.0.1), só enquanto não existe nenhuma
conta e só nos jeitos locais de rodar. Depois da primeira conta, ela não volta.

## Onde fica cada coisa

| O quê | Onde |
|---|---|
| Configuração (chave secreta, modelo) | `~/.visao/.env`, criado na primeira abertura |
| Banco de dados | `~/.visao/dados/visao.db` |
| Log do servidor aberto pelo app | `~/.visao/visao-app.log` |
| O servidor congelado | dentro do app, `Visão.app/Contents/Resources/visao-servidor/` |

É a mesma pasta do instalador e do serviço ([INSTALAR.md](INSTALAR.md)): dá para usar o app, o
comando `visao` e o serviço com os mesmos dados.

## Como ele se comporta

- **Já existe um Visão rodando** (o serviço, ou um `visao iniciar` no Terminal): o app só abre a
  janela nele e não o desliga ao fechar.
- **Não existe:** o app sobe o servidor de dentro na porta 8000 (ou noutra livre, se a 8000 estiver
  ocupada) e o desliga quando você fecha o app. O worker (pensar, estudar, conferir painéis) só
  trabalha com o app aberto. Para ele trabalhar sempre, instale o serviço e use o app como janela.
- **Se o servidor não subir,** a janela diz o motivo e onde está o log.

## O que ainda não vem no app

- **Voz** (Kokoro e Whisper, cerca de 2 GB) e o **navegador ao vivo** (Playwright e Chromium).
  Os dois continuam no Visão instalado pelo script.
- **Mac Intel.**
- **Assinatura e notarização da Apple** (US$ 99 por ano). Quando houver, entram como segredos no
  CI; o app não muda.

## Peças

| Peça | Onde |
|---|---|
| O servidor congelado | [`desktop/visao-servidor.spec`](../desktop/visao-servidor.spec), [`desktop/visao_servidor.py`](../desktop/visao_servidor.py) |
| O app (Tauri) | [`desktop/app/`](../desktop/app/): `src-tauri/src/main.rs`, a página de espera em `ui/` |
| Build e teste | [`desktop/construir.sh`](../desktop/construir.sh), [`.github/workflows/desktop.yml`](../.github/workflows/desktop.yml) |
| O `visao` congelado | [`apps/visao_cli.py`](../apps/visao_cli.py) (`FROZEN`, `.env` em `~/.visao`) |
| Primeira conta | `GET`/`POST /auth/first-run` em [`apps/api/routes/auth.py`](../apps/api/routes/auth.py), a tela em `apps/web/src/components/Login.tsx` |
| O ícone | `desktop/app/app-icon.png`, gerado por [`brand/generate_assets.py`](../brand/generate_assets.py) na grade da Apple |
