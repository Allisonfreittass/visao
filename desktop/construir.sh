#!/bin/bash
# Builds the Visão's Mac app (docs/APP_MAC.md, ADR-0027), on a Mac or in CI (.github/workflows/desktop.yml):
#
#   bash desktop/construir.sh            # the whole app: desktop/app/Visao-mac.zip
#   bash desktop/construir.sh --servidor # only the frozen server, tested (runs on Linux too)
#
# 1. the web build (Node 22+);
# 2. the server frozen by PyInstaller, in folder mode (desktop/visao-servidor.spec), in a Python
#    3.12 of its own (.build/venv, made with uv) with the locked dependencies;
# 3. a real start of the frozen server with an empty home: migrates, answers, serves the site;
# 4. the Tauri app around it (Rust), zipped with ditto so the bundle keeps its signature.
#
# Written for the bash 3.2 of macOS.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
only_server=0
[ "${1:-}" = "--servidor" ] && only_server=1
build="$root/.build"
venv="$build/venv"
out="$root/desktop/app/servidor"

say() { printf '\n== %s\n' "$*"; }
die() { printf 'Erro: %s\n' "$*" >&2; exit 1; }
command -v uv >/dev/null 2>&1 || die "falta o uv (curl -LsSf https://astral.sh/uv/install.sh | sh)."
command -v npm >/dev/null 2>&1 || die "falta o Node 22 ou mais novo."

say "Build do web"
npm --prefix "$root/apps/web" ci --silent --no-audit --no-fund
npm --prefix "$root/apps/web" run --silent build

say "Servidor congelado (PyInstaller)"
[ -x "$venv/bin/python" ] || uv venv --quiet --python 3.12 "$venv"
uv pip install --quiet --python "$venv/bin/python" \
  -c "$root/infrastructure/deployment/constraints.txt" "$root" "pyinstaller==6.22.3"
rm -rf "$out"
(cd "$root" && "$venv/bin/pyinstaller" --noconfirm --log-level WARN \
  --distpath "$out" --workpath "$build/pyinstaller" desktop/visao-servidor.spec)
du -sh "$out/visao-servidor"

say "Teste do servidor congelado"
home="$(mktemp -d)"
port=8799
server="$out/visao-servidor/visao-servidor"
stop() { env -i HOME="$home" VISAO_HOME="$home" PATH=/usr/bin:/bin "$server" parar >/dev/null 2>&1 || true; }
trap stop EXIT
# An empty environment: no Python, no Node, no .env. It has to stand on its own.
env -i HOME="$home" VISAO_HOME="$home" PATH=/usr/bin:/bin "$server" iniciar --porta "$port" --fundo \
  || { cat "$home/visao.log" >&2; die "o servidor congelado não subiu"; }
curl -fsS "http://127.0.0.1:$port/api/health" | grep -q '"ok"' || die "não respondeu /api/health"
curl -fsS "http://127.0.0.1:$port/api/auth/first-run" | grep -q '"needed":true' \
  || die "a tela de primeiro uso não está aberta"
curl -fsS -H 'Accept: text/html' "http://127.0.0.1:$port/" | grep -qi '<!doctype html>' \
  || die "o site não veio"
stop
trap - EXIT
rm -rf "$home"
echo "O servidor congelado sobe, migra, responde e serve o site."

[ "$only_server" = 1 ] && exit 0
[ "$(uname -s)" = Darwin ] || die "o app (Tauri) só é montado no macOS; use --servidor aqui."
command -v cargo >/dev/null 2>&1 || die "falta o Rust (https://rustup.rs)."

say "App (Tauri)"
npm --prefix "$root/desktop/app" ci --silent --no-audit --no-fund
(cd "$root/desktop/app" && npx tauri build --bundles app)
app="$root/desktop/app/src-tauri/target/release/bundle/macos/Visão.app"
[ -d "$app" ] || die "o app não saiu em $app"
say "Teste do app"
# Opened for real, with an empty home: it has to find the server inside it, start it, and stop
# it when it quits. Nothing else may be answering on the usual port.
if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  die "já há um Visão na porta 8000; pare-o (visao parar) para testar o app"
fi
home="$(mktemp -d)"
VISAO_HOME="$home" "$app/Contents/MacOS/visao-app" >/dev/null 2>&1 &
app_pid=$!
up=0
for _ in $(seq 1 240); do
  if curl -fsS http://127.0.0.1:8000/api/health 2>/dev/null | grep -q '"ok"'; then up=1; break; fi
  kill -0 "$app_pid" 2>/dev/null || break
  sleep 0.5
done
[ "$up" = 1 ] || { cat "$home/visao-app.log" >&2 || true; kill "$app_pid" 2>/dev/null || true; die "o app não subiu o servidor"; }
echo "O app subiu o servidor que leva dentro."
osascript -e 'tell application id "digital.visao.mac" to quit' || kill "$app_pid"
for _ in $(seq 1 60); do
  curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 || break
  sleep 0.5
done
if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  VISAO_HOME="$home" "$out/visao-servidor/visao-servidor" parar || true
  die "o servidor continuou rodando depois de fechar o app"
fi
echo "Ao fechar o app, o servidor parou junto."
rm -rf "$home"

rm -f "$root/desktop/app/Visao-mac.zip"
ditto -c -k --keepParent "$app" "$root/desktop/app/Visao-mac.zip"
du -sh "$app" "$root/desktop/app/Visao-mac.zip"
echo "Pronto: $root/desktop/app/Visao-mac.zip"
