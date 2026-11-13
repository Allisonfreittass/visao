#!/usr/bin/env python3
"""O braço do Visão no Mac (docs/BRACO.md). Só biblioteca padrão: roda com o Python do sistema.

Busca no servidor tarefas que você aprovou, roda o Claude Code no projeto pedido, com uma lista
fechada de ferramentas, e devolve o resultado. Só faz requisições de saída: nenhuma porta aberta.

O que é permitido fica aqui no Mac, em ~/.config/visao/braco.json; o servidor não muda isso.
Uso: python3 visao_braco.py [--config caminho] [--once]
"""

# The system Python on macOS is 3.9: without this, `dict | None` in a signature fails at import.
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "1"
DEFAULT_CONFIG = Path("~/.config/visao/braco.json").expanduser()
HEARTBEAT_SECONDS = 60
LONG_POLL_SECONDS = 25
MAX_RESULT = 200_000

# Read, search and edit inside the project, plus inspection and test commands. Everything else
# is denied without asking (`dontAsk`): no network, no deleting, no pushing, no sudo.
DEFAULT_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash(git status)",
    "Bash(git status *)",
    "Bash(git diff *)",
    "Bash(git log *)",
    "Bash(ls *)",
    "Bash(npm test *)",
    "Bash(npm run *)",
    "Bash(make test *)",
    "Bash(make check *)",
    "Bash(pytest *)",
    "Bash(.venv/bin/pytest *)",
]
NEVER = ["Bash(rm *)", "Bash(sudo *)", "Bash(curl *)", "Bash(wget *)", "Bash(git push *)"]
SYSTEM_NOTE = (
    "Esta tarefa veio do Visão, o assistente pessoal do dono deste Mac, e foi aprovada por ele. "
    "Trabalhe só dentro deste projeto. No fim, responda em português do Brasil com um resumo "
    "curto: o que mudou, onde, e o que ficou pendente ou precisa da decisão dele."
)


@dataclass
class Config:
    server: str
    token: str
    projects: dict[str, Path]
    claude: str = "claude"
    allowed_tools: list[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))
    max_turns: int = 30
    max_budget_usd: float = 2.0
    timeout_minutes: int = 30
    use_api_key: bool = False

    @classmethod
    def load(cls, path: Path) -> Config:
        data = json.loads(path.read_text())
        projects = {
            str(name): Path(folder).expanduser().resolve()
            for name, folder in (data.get("projects") or {}).items()
        }
        if not data.get("server") or not data.get("token"):
            raise ValueError("braco.json precisa de server e token")
        if not projects:
            raise ValueError("braco.json precisa de pelo menos um projeto em projects")
        return cls(
            server=str(data["server"]).rstrip("/"),
            token=str(data["token"]),
            projects=projects,
            claude=str(data.get("claude", "claude")),
            allowed_tools=list(data.get("allowed_tools") or DEFAULT_TOOLS),
            max_turns=int(data.get("max_turns", 30)),
            max_budget_usd=float(data.get("max_budget_usd", 2.0)),
            timeout_minutes=int(data.get("timeout_minutes", 30)),
            use_api_key=bool(data.get("use_api_key", False)),
        )


def call(config: Config, method: str, path: str, body: dict | None = None, timeout: float = 40):
    request = urllib.request.Request(  # noqa: S310 (the owner's own server, from braco.json)
        f"{config.server}/api/arm{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"visao-braco/{VERSION}",
            "X-Visao-Arm-Token": config.token,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        raw = response.read()
    return json.loads(raw) if raw else None


def command(config: Config, task: dict) -> list[str]:
    """The prompt goes on stdin, so no flag can ever swallow it or be injected through it."""
    args = [
        config.claude,
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        ",".join(config.allowed_tools),
        "--disallowedTools",
        ",".join(NEVER),
        "--max-turns",
        str(config.max_turns),
        "--max-budget-usd",
        str(config.max_budget_usd),
        "--append-system-prompt",
        SYSTEM_NOTE,
    ]
    if task.get("resume_session"):
        args += ["--resume", str(task["resume_session"])]
    return args


def _environment(config: Config) -> dict[str, str]:
    env = dict(os.environ)
    if not config.use_api_key:
        # With a key in the environment `claude -p` always uses it; without, your login.
        env.pop("ANTHROPIC_API_KEY", None)
    return env


def run_claude(config: Config, task: dict, folder: Path) -> dict:
    """Runs one task and returns the body for /result. Never raises for a task failure."""
    try:
        process = subprocess.Popen(  # noqa: S603 (fixed argv; the prompt goes on stdin)
            command(config, task),
            cwd=folder,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_environment(config),
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"Não achei o Claude Code ({config.claude}) neste Mac."}
    try:
        out, err = process.communicate(task["prompt"], timeout=config.timeout_minutes * 60)
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGINT)  # ends the turn cleanly
        try:
            out, err = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            out, err = process.communicate()
        return {
            "ok": False,
            "error": f"Passou de {config.timeout_minutes} min e eu interrompi.",
            "result": (out or "")[-MAX_RESULT:],
        }
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        detail = (err or out or "").strip()[-400:]
        return {
            "ok": False,
            "error": f"O Claude Code saiu com erro: {detail or process.returncode}",
        }
    failed = process.returncode != 0 or bool(data.get("is_error"))
    body = {
        "ok": not failed,
        "result": str(data.get("result") or "")[:MAX_RESULT],
        "session_id": data.get("session_id"),
        "cost_usd": data.get("total_cost_usd"),
    }
    if failed:
        body["error"] = str(data.get("subtype") or data.get("result") or "falhou")[:500]
    return body


def handle(config: Config, task: dict) -> dict:
    folder = config.projects.get(task.get("project", ""))
    if folder is None:
        names = ", ".join(sorted(config.projects)) or "nenhum"
        return {"ok": False, "error": f"Projeto não liberado neste Mac. Liberados: {names}."}
    if not folder.is_dir():
        return {"ok": False, "error": f"A pasta do projeto não existe: {folder}"}
    return run_claude(config, task, folder)


def heartbeat(config: Config) -> None:
    call(
        config,
        "POST",
        "/device/heartbeat",
        {"projects": sorted(config.projects), "version": VERSION},
    )


def loop(config: Config, once: bool = False) -> None:
    backoff, last_beat = 5, 0.0
    while True:
        try:
            if time.monotonic() - last_beat > HEARTBEAT_SECONDS:
                heartbeat(config)
                last_beat = time.monotonic()
            task = call(config, "GET", f"/device/next?wait={LONG_POLL_SECONDS}")
            backoff = 5
            if task:
                print(f"Tarefa {task['id']} em {task['project']}", flush=True)
                result = handle(config, task)
                call(config, "POST", f"/device/tasks/{task['id']}/result", result, timeout=60)
                print(f"Tarefa {task['id']}: {'ok' if result['ok'] else 'falhou'}", flush=True)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                print("Token recusado: pareie este Mac de novo na interface.", file=sys.stderr)
                return
            print(f"Servidor respondeu {exc.code}; tento de novo em {backoff}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"Sem conexão ({exc}); tento de novo em {backoff}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
        if once:
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--once", action="store_true", help="uma rodada só (para testar)")
    args = parser.parse_args(argv)
    try:
        config = Config.load(args.config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Configuração inválida em {args.config}: {exc}", file=sys.stderr)
        return 2
    print(f"Braço {VERSION} ligado a {config.server}; projetos: {', '.join(config.projects)}")
    loop(config, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
