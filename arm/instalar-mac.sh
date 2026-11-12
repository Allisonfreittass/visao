#!/bin/bash
# Instala o braço do Visão no Mac (docs/BRACO.md): copia o script para ~/.config/visao, cria a
# configuração se não existir e deixa o launchd mantendo ele ligado (reinicia se cair, sobe no
# login). Rodar de dentro do repositório:  bash arm/instalar-mac.sh
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
dir="$HOME/.config/visao"
plist="$HOME/Library/LaunchAgents/digital.visao.braco.plist"
label=digital.visao.braco

mkdir -p "$dir" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
chmod 700 "$dir"
install -m 700 "$here/visao_braco.py" "$dir/visao_braco.py"
if [ ! -f "$dir/braco.json" ]; then
  install -m 600 "$here/braco.example.json" "$dir/braco.json"
  echo "Criei $dir/braco.json: cole o token do pareamento e ajuste os projetos, depois rode de novo."
  exit 0
fi
chmod 600 "$dir/braco.json"

claude_path=$(command -v claude || true)
[ -n "$claude_path" ] || { echo "Instale o Claude Code e faça login (claude) antes." >&2; exit 1; }
python=$(command -v python3)

cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array><string>$python</string><string>$dir/visao_braco.py</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$(dirname "$claude_path"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/visao-braco.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/visao-braco.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "Braço ligado. Log: tail -f ~/Library/Logs/visao-braco.log"
echo "Para desligar: launchctl bootout gui/$(id -u)/$label"
