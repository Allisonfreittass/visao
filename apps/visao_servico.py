"""The Visão as a service of the owner's own system (docs/research/execucao_local.md, etapa 5):
started at login and started again if it falls, the way the arm already runs on the Mac
(arm/instalar-mac.sh) and the way OpenClaw and Hermes register their gateways.

- macOS: a launchd LaunchAgent, ~/Library/LaunchAgents/digital.visao.app.plist (KeepAlive);
- Linux: a systemd user unit, ~/.config/systemd/user/visao.service (Restart=on-failure).

The service runs `visao iniciar` in the foreground with VISAO_SERVICO=1, so the command knows it
is the service and does not hand the start back to it. VISAO_SERVICO_NOME changes the label or the
unit name (tests and a second install use it).
"""

import os
import platform
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

DEFAULT_PORT = 8000


def kind() -> str | None:
    system = platform.system()
    if system == "Darwin":
        return "launchd"
    if system == "Linux":
        return "systemd"
    return None


def label() -> str:
    """launchd's label; on Linux, the unit's name."""
    custom = os.environ.get("VISAO_SERVICO_NOME")
    if custom:
        return custom
    return "digital.visao.app" if kind() == "launchd" else "visao"


def path() -> Path:
    if kind() == "launchd":
        return Path.home() / "Library" / "LaunchAgents" / f"{label()}.plist"
    return Path.home() / ".config" / "systemd" / "user" / f"{label()}.service"


def installed() -> bool:
    return path().is_file()


def _command(root: Path, port: int) -> list[str]:
    return [sys.executable, "-m", "apps.visao_cli", "iniciar", "--porta", str(port)]


def plist_text(root: Path, port: int, home: Path, log: Path) -> str:
    args = "".join(f"<string>{escape(a)}</string>" for a in _command(root, port))
    env = {
        "VISAO_SERVICO": "1",
        "VISAO_HOME": str(home),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
    }
    env_xml = "".join(f"<key>{k}</key><string>{escape(v)}</string>" for k, v in env.items())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{escape(label())}</string>
  <key>ProgramArguments</key>
  <array>{args}</array>
  <key>WorkingDirectory</key><string>{escape(str(root))}</string>
  <key>EnvironmentVariables</key>
  <dict>{env_xml}</dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>{escape(str(log))}</string>
  <key>StandardErrorPath</key><string>{escape(str(log))}</string>
</dict>
</plist>
"""


def unit_text(root: Path, port: int, home: Path, log: Path) -> str:
    command = " ".join(_command(root, port))
    return f"""[Unit]
Description=Visão, o agente pessoal (http://127.0.0.1:{port})
After=network-online.target

[Service]
Type=simple
WorkingDirectory={root}
Environment=VISAO_SERVICO=1
Environment=VISAO_HOME={home}
ExecStart={command}
Restart=on-failure
RestartSec=30
TimeoutStopSec=30
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=default.target
"""


def run(command: list[str]) -> int:
    """The system's service manager; a test replaces it."""
    return subprocess.run(command, check=False).returncode  # noqa: S603


def _gui() -> str:
    return f"gui/{os.getuid()}"


def instalar(root: Path, port: int, home: Path, log: Path) -> int:
    manager = kind()
    if manager is None:
        print("Serviço só no macOS (launchd) e no Linux (systemd).", file=sys.stderr)
        return 1
    home.mkdir(parents=True, exist_ok=True)
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if manager == "launchd":
        target.write_text(plist_text(root, port, home, log))
        run(["launchctl", "bootout", f"{_gui()}/{label()}"])  # an older one, if loaded
        code = run(["launchctl", "bootstrap", _gui(), str(target)])
    else:
        target.write_text(unit_text(root, port, home, log))
        run(["systemctl", "--user", "daemon-reload"])
        code = run(["systemctl", "--user", "enable", f"{label()}.service"])
        if code == 0:  # restart, not start: after an update, the running one has the old code
            code = run(["systemctl", "--user", "restart", f"{label()}.service"])
    if code != 0:
        print(f"O serviço foi escrito em {target}, mas não ligou (código {code}).", file=sys.stderr)
        return 1
    print(f"Serviço ligado ({manager}): sobe com o login e volta sozinho se cair.")
    print(f"Arquivo: {target}")
    if manager == "systemd":
        print("Para ele rodar também sem você logado: loginctl enable-linger $USER")
    return 0


def remover() -> int:
    manager = kind()
    target = path()
    if manager is None or not target.is_file():
        print("Não há serviço do Visão instalado.")
        return 0
    if manager == "launchd":
        run(["launchctl", "bootout", f"{_gui()}/{label()}"])
    else:
        run(["systemctl", "--user", "disable", "--now", f"{label()}.service"])
    target.unlink()
    if manager == "systemd":
        run(["systemctl", "--user", "daemon-reload"])
    print("Serviço removido. O Visão não sobe mais sozinho.")
    return 0


def start() -> int:
    """Starts the installed service (it runs `visao iniciar` itself)."""
    if kind() == "launchd":
        code = run(["launchctl", "bootstrap", _gui(), str(path())])
        # Already loaded: ask it to run now.
        return 0 if code == 0 else run(["launchctl", "kickstart", f"{_gui()}/{label()}"])
    return run(["systemctl", "--user", "start", f"{label()}.service"])


def stop() -> int:
    """Stops the installed service. A plain SIGTERM would only make the manager start it again."""
    if kind() == "launchd":
        return run(["launchctl", "bootout", f"{_gui()}/{label()}"])
    return run(["systemctl", "--user", "stop", f"{label()}.service"])
