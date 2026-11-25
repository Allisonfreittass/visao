#!/bin/bash
# Instala o Visão nesta máquina (docs/INSTALAR.md), no macOS ou no Linux, como o Hermes e o braço:
#
#   curl -fsSL https://raw.githubusercontent.com/Allisonfreittass/visao/main/scripts/instalar.sh | bash
#   bash scripts/instalar.sh [--sem-servico]        # de dentro de um checkout
#
# O que faz, sem sudo e só dentro da sua pasta pessoal:
#   1. instala o uv (o gerenciador de Python da Astral) se ele não existir;
#   2. clona o Visão em ~/.visao/visao (ou atualiza, se já estiver lá);
#   3. cria o Python 3.12 do Visão e instala as dependências travadas;
#   4. gera o build do web (precisa do Node 22 ou mais novo);
#   5. cria o .env com uma chave secreta nova e o banco em ~/.visao/dados (só na primeira vez);
#   6. põe o comando `visao` em ~/.local/bin;
#   7. liga o serviço do sistema (launchd ou systemd do usuário), a não ser com --sem-servico.
#
# Variáveis: VISAO_HOME (padrão ~/.visao), VISAO_REPO, VISAO_REF (padrão main), VISAO_BIN_DIR.
# Escrito para o bash 3.2 do macOS; roda também no Linux.
set -euo pipefail

repo=${VISAO_REPO:-https://github.com/Allisonfreittass/visao.git}
ref=${VISAO_REF:-main}
home=${VISAO_HOME:-$HOME/.visao}
code="$home/visao"
data="$home/dados"
bin_dir=${VISAO_BIN_DIR:-$HOME/.local/bin}
with_service=1
for arg in "$@"; do
  case "$arg" in
    --sem-servico) with_service=0 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }
die() { printf 'Erro: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "falta o $1. $2"; }

case "$(uname -s)" in
  Darwin|Linux) ;;
  *) die "só macOS e Linux por enquanto." ;;
esac
need git "Instale o git e rode de novo."
need curl "Instale o curl e rode de novo."

say "uv"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
need uv "A instalação do uv não deixou o comando no PATH; abra um terminal novo e rode de novo."
uv --version

say "Código em $code"
mkdir -p "$home"
chmod 700 "$home"
if [ -d "$code/.git" ]; then
  git -C "$code" fetch --quiet --depth 1 origin "$ref"
  git -C "$code" checkout --quiet --force FETCH_HEAD
else
  git clone --quiet --depth 1 --branch "$ref" "$repo" "$code"
fi
git -C "$code" log --oneline -1

say "Python 3.12 e dependências"
[ -x "$code/.venv/bin/python" ] || uv venv --quiet --python 3.12 "$code/.venv"
uv pip install --quiet --python "$code/.venv/bin/python" \
  -c "$code/infrastructure/deployment/constraints.txt" -e "$code"

say "Build do web"
node_major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
if [ "$node_major" -lt 22 ]; then
  die "o build do web precisa do Node 22 ou mais novo (achei: ${node_major}). No Mac: brew install node; no Linux: https://nodejs.org. Depois rode de novo."
fi
npm --prefix "$code/apps/web" ci --silent --no-audit --no-fund
npm --prefix "$code/apps/web" run --silent build

say "Configuração"
mkdir -p "$data"
chmod 700 "$data"
if [ ! -f "$code/.env" ]; then
  "$code/.venv/bin/python" - "$code/.env.example" "$code/.env" "$data/visao.db" <<'PY'
import secrets
import sys

example, target, database = sys.argv[1:]
lines = []
for line in open(example, encoding="utf-8").read().splitlines():
    if line.startswith("VISION_SECRET_KEY="):
        line = "VISION_SECRET_KEY=" + secrets.token_urlsafe(48)
    elif line.startswith("VISION_DATABASE_URL="):
        line = "VISION_DATABASE_URL=sqlite:///" + database
    lines.append(line)
with open(target, "w", encoding="utf-8") as out:
    out.write("\n".join(lines) + "\n")
PY
  chmod 600 "$code/.env"
  echo "Criei $code/.env (chave secreta nova, banco em $data/visao.db)."
  fresh_env=1
else
  echo "Mantive o $code/.env que já existia."
  fresh_env=0
fi

say "Comando visao"
mkdir -p "$bin_dir"
ln -sf "$code/.venv/bin/visao" "$bin_dir/visao"
echo "$bin_dir/visao"
case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo "Aviso: $bin_dir não está no PATH. Acrescente ao seu ~/.zshrc ou ~/.bashrc:"
     echo "  export PATH=\"$bin_dir:\$PATH\"" ;;
esac

if [ "$with_service" = 1 ]; then
  say "Serviço"
  VISAO_HOME="$home" "$code/.venv/bin/visao" servico instalar
fi

say "Pronto"
if [ "$fresh_env" = 1 ]; then
  echo "Falta preencher o modelo em $code/.env (o bloco VISION_LLM_*, docs/MODEL_SELECTION.md)."
fi
echo "Crie o seu usuário:  visao conta criar --email voce@exemplo.com"
if [ "$with_service" = 1 ]; then
  echo "Depois:              visao parar && visao iniciar   (para ler o .env novo)"
else
  echo "Depois:              visao iniciar --fundo"
fi
echo "E abra:              http://127.0.0.1:8000"
