# Instalar o Visão na sua máquina

> Etapa 5 de [research/execucao_local.md](research/execucao_local.md), em 2026-11-25. Um script,
> sem Docker e sem sudo, nos moldes do Hermes e do instalador do braço ([BRACO.md](BRACO.md)).

```bash
curl -fsSL https://raw.githubusercontent.com/Allisonfreittass/visao/main/scripts/instalar.sh | bash
```

Precisa de git, curl e Node 22 ou mais novo (para o build do web; no Mac, `brew install node`).
O Python não: o script instala o [uv](https://docs.astral.sh/uv/) e ele baixa o Python 3.12 só
para o Visão.

## O que ele faz

| Passo | Onde |
|---|---|
| Instala o `uv`, se faltar | `~/.local/bin/uv` |
| Clona o Visão (ou atualiza, se já estiver lá) | `~/.visao/visao` |
| Cria o Python 3.12 e instala as dependências travadas (`infrastructure/deployment/constraints.txt`) | `~/.visao/visao/.venv` |
| Gera o build do web | `~/.visao/visao/apps/web/dist` |
| Cria o `.env` com uma chave secreta nova e o banco SQLite fora do código (só na primeira vez; depois mantém o seu) | `~/.visao/visao/.env`, `~/.visao/dados/visao.db` |
| Põe o comando `visao` no PATH | `~/.local/bin/visao` |
| Liga o serviço do sistema | macOS: `~/Library/LaunchAgents/digital.visao.app.plist`; Linux: `~/.config/systemd/user/visao.service` |

`~/.visao` e `~/.visao/dados` ficam só com permissão sua (700) e o `.env` com 600.

## Depois de instalar

1. Preencha o bloco `VISION_LLM_*` em `~/.visao/visao/.env` ([MODEL_SELECTION.md](MODEL_SELECTION.md)).
2. Reinicie para ler o `.env` novo: `visao parar && visao iniciar`.
3. Abra http://127.0.0.1:8000: na primeira vez, a tela de entrar cria a sua conta e faz a gênese
   ([ADR-0027](decisions/0027-app-de-mac.md)). Pelo terminal também dá:
   `visao conta criar --email voce@exemplo.com`.

## O serviço

O serviço roda `visao iniciar` na pasta do código, sobe quando você entra na sua conta e volta
sozinho se o processo cair (launchd com `KeepAlive`; systemd com `Restart=on-failure`, 30 s
depois). Com ele instalado, `visao iniciar` e `visao parar` pedem ao sistema, em vez de abrir ou
matar o processo por conta própria: um `kill` simples só faria o sistema subir outro.

```bash
visao estado              # rodando ou não, respondendo ou não, e se o serviço está instalado
visao servico remover     # desliga e apaga o serviço; o Visão continua instalado
visao servico instalar    # liga de novo (reinicia, se já estava ligado)
```

No Linux, o systemd do usuário para quando você sai da sessão. Para o Visão rodar também sem você
logado: `loginctl enable-linger $USER`.

## Opções

```bash
bash scripts/instalar.sh --sem-servico     # sem o serviço: suba com `visao iniciar --fundo`
VISAO_HOME=~/outro-lugar bash scripts/instalar.sh
VISAO_REF=uma-branch bash scripts/instalar.sh
```

`VISAO_REPO` troca o repositório e `VISAO_BIN_DIR` a pasta do comando. `VISAO_SERVICO_NOME` dá
outro nome ao serviço (útil para uma segunda instalação na mesma máquina).

## Atualizar e desinstalar

Atualizar é rodar o script de novo: ele baixa o código novo, reinstala as dependências, refaz o
build, mantém o `.env` e o banco e reinicia o serviço (as migrações rodam quando ele sobe).

Desinstalar: `visao servico remover`, depois apague `~/.visao` (o banco vai junto; copie
`~/.visao/dados` antes se quiser guardar) e o link `~/.local/bin/visao`.
