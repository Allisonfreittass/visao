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
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

# 2: runs Claude Code isolated, keeps results until the server takes them, beats while working,
# and can answer with a local model.
VERSION = "2"
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
# What a task must never change, because it would widen what the NEXT tasks may do: permission
# rules and hooks (.claude/), MCP servers (.mcp.json), instructions read at the start of every
# task (CLAUDE.md) and git hooks (.git/). Denied even if allowed_tools says otherwise.
PROTECTED = [".claude/**", ".mcp.json", "**/CLAUDE.md", "**/CLAUDE.local.md", ".git/**"]
NEVER = [
    "Bash(rm *)",
    "Bash(sudo *)",
    "Bash(curl *)",
    "Bash(wget *)",
    "Bash(git push *)",
    *(f"{tool}({path})" for tool in ("Edit", "Write") for path in PROTECTED),
]
TOO_OLD = (
    "Este Claude Code não tem como rodar isolado (falta --restricted ou --setting-sources), "
    "então não rodei nada. Atualize com `claude update` e peça de novo."
)
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
    # The local model (docs/MODELO_LOCAL.md): {"modelo": "qwen3:4b", "endereco": Ollama's
    # address on this Mac}. Unset: this Mac offers no local model.
    local_model: str | None = None
    ollama: str = "http://127.0.0.1:11434"
    local_context: int = 16384
    # Where results wait until the server takes them, next to braco.json.
    state_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG.parent)

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
        local = data.get("modelo_local") or {}
        if not isinstance(local, dict):
            raise ValueError("modelo_local precisa ser um objeto, como no exemplo")
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
            local_model=(str(local["modelo"]).strip() or None) if local.get("modelo") else None,
            ollama=_local_address(str(local.get("endereco") or "http://127.0.0.1:11434")),
            local_context=int(local.get("contexto", 16384)),
            state_dir=path.expanduser().resolve().parent,
        )


def _local_address(address: str) -> str:
    """The questions carry the owner's conversations: they only go to a model on this Mac."""
    address = address.rstrip("/")
    host = address.split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[0]
    if host not in ("127.0.0.1", "localhost", "[::1]"):
        raise ValueError("modelo_local.endereco precisa ser deste Mac (127.0.0.1 ou localhost)")
    return address


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


_help_text: dict[str, str] = {}


def _help(claude: str) -> str:
    if claude not in _help_text:
        try:
            done = subprocess.run(  # noqa: S603 (the configured claude, fixed argv)
                [claude, "--help"], capture_output=True, text=True, timeout=30
            )
            _help_text[claude] = done.stdout or ""
        except (OSError, subprocess.TimeoutExpired):
            return ""  # not cached: maybe it is being installed
    return _help_text[claude]


def _has(help_text: str, flag: str) -> bool:
    return re.search(rf"^\s+(?:-\w, )?{re.escape(flag)}\b", help_text, re.MULTILINE) is not None


def isolation(config: Config) -> list[str] | None:
    """Flags that keep a task from loading, or changing, what governs the next tasks: project
    settings and hooks, MCP servers, files of settings and git. None when this Claude Code
    cannot run isolated; then nothing runs."""
    text = _help(config.claude)
    tools = ",".join(sorted({t.split("(", 1)[0] for t in config.allowed_tools}))
    if _has(text, "--restricted"):
        # Ignores user, project and local settings; confines file tools to the project; only a
        # person or the permission handler may approve writes to settings, git and tool files
        # (none here: dontAsk denies). It removes Bash unless --tools names it.
        return ["--restricted", "--strict-mcp-config", "--tools", tools]
    if _has(text, "--setting-sources") and _has(text, "--strict-mcp-config"):
        # Older Claude Code: your own settings only, no hooks, no MCP servers.
        flags = [
            "--setting-sources",
            "user",
            "--settings",
            json.dumps({"disableAllHooks": True}),
            "--strict-mcp-config",
        ]
        return flags + (["--tools", tools] if _has(text, "--tools") else [])
    return None


def command(config: Config, task: dict, isolated: list[str]) -> list[str]:
    """The prompt goes on stdin, so no flag can ever swallow it or be injected through it."""
    args = [
        config.claude,
        "-p",
        *isolated,
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


def run_claude(config: Config, task: dict, folder: Path, isolated: list[str]) -> dict:
    """Runs one task and returns the body for /result. Never raises for a task failure."""
    try:
        process = subprocess.Popen(  # noqa: S603 (fixed argv; the prompt goes on stdin)
            command(config, task, isolated),
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
    isolated = isolation(config)
    if isolated is None:
        missing = f"Não achei o Claude Code ({config.claude}) neste Mac."
        return {"ok": False, "error": TOO_OLD if _help(config.claude) else missing}
    return run_claude(config, task, folder, isolated)


def heartbeat(config: Config, running: str | None = None) -> None:
    """`running`: the task being worked on now, so the server knows it is not lost."""
    call(
        config,
        "POST",
        "/device/heartbeat",
        {"projects": sorted(config.projects), "version": VERSION, "running": running},
    )


@contextmanager
def beating(config: Config, task_id: str):
    """Keeps the heartbeat going while a task runs (it can take 30 min): without it the server
    cannot tell a long task from a Mac that died."""
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                heartbeat(config, running=task_id)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                pass  # the next beat tries again; the task goes on

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(5)


# Results are written here before they are sent, and removed only once the server took them: a
# network drop after a 30-minute task no longer throws the result away.
def _outbox(config: Config) -> Path:
    folder = config.state_dir / "saida"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _running_file(config: Config) -> Path:
    return config.state_dir / "em-andamento.json"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".tmp")
    partial.write_text(json.dumps(data))
    os.replace(partial, path)


def keep(config: Config, task_id: str, result: dict) -> None:
    _write(_outbox(config) / f"{task_id}.json", {"task_id": task_id, "result": result})
    _running_file(config).unlink(missing_ok=True)


def recover(config: Config) -> None:
    """A task that was running when the Mac or the arm stopped is reported as cut off. It is
    never run again on its own: it may have changed files halfway."""
    running = _running_file(config)
    try:
        task_id = json.loads(running.read_text())["task_id"]
    except (OSError, ValueError, KeyError, TypeError):
        running.unlink(missing_ok=True)
        return
    print(f"Tarefa {task_id} foi interrompida quando o braço parou", flush=True)
    keep(config, task_id, {"ok": False, "error": CUT_OFF})


CUT_OFF = (
    "O Mac desligou ou o braço reiniciou no meio desta tarefa. Nada foi refeito; confira o "
    "projeto (git status) antes de pedir de novo."
)


def deliver(config: Config) -> None:
    """Sends every result still waiting, oldest first. A network error stops here and is raised
    (the loop waits and tries again); a result the server refuses for good is dropped."""
    for path in sorted(_outbox(config).glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            data = json.loads(path.read_text())
            task_id, result = str(data["task_id"]), dict(data["result"])
        except (OSError, ValueError, KeyError, TypeError):
            path.unlink(missing_ok=True)
            continue
        try:
            call(config, "POST", f"/device/tasks/{task_id}/result", result, timeout=60)
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 409, 422):
                raise
            print(f"O servidor recusou o resultado de {task_id} ({exc.code})", file=sys.stderr)
        path.unlink(missing_ok=True)
        print(f"Tarefa {task_id}: {'ok' if result.get('ok') else 'falhou'}", flush=True)


def work(config: Config, task: dict) -> None:
    task_id = str(task["id"])
    print(f"Tarefa {task_id} em {task.get('project')}", flush=True)
    _write(_running_file(config), {"task_id": task_id})
    with beating(config, task_id):
        result = handle(config, task)
    keep(config, task_id, result)


def loop(config: Config, once: bool = False) -> None:
    backoff, last_beat = 5, 0.0
    recover(config)
    while True:
        try:
            deliver(config)
            if time.monotonic() - last_beat > HEARTBEAT_SECONDS:
                heartbeat(config)
                last_beat = time.monotonic()
            task = call(config, "GET", f"/device/next?wait={LONG_POLL_SECONDS}")
            backoff = 5
            if task:
                work(config, task)
                deliver(config)
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


def ask_local_model(config: Config, question: dict) -> dict:
    """One question to the model on this Mac (Ollama's own API: it takes the context size and
    turns Qwen's long thinking off). Errors are reported, never raised."""
    body = {
        "model": config.local_model,
        "messages": question.get("messages") or [],
        "stream": False,
        "think": False,
        "options": {
            "num_ctx": config.local_context,
            "num_predict": int(question.get("max_output_tokens") or 1024),
        },
    }
    request = urllib.request.Request(  # noqa: S310 (Ollama on this Mac, checked at load)
        f"{config.ollama}/api/chat",
        method="POST",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
            data = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        return {"ok": False, "error": f"Ollama respondeu {exc.code}: {detail}"}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"ok": False, "error": f"Ollama não respondeu ({exc}). Ele está aberto?"}
    text = ((data.get("message") or {}).get("content") or "").strip()
    if not text:
        return {"ok": False, "error": "O modelo local não escreveu nada."}
    return {
        "ok": True,
        "text": text,
        "input_tokens": int(data.get("prompt_eval_count") or 0),
        "output_tokens": int(data.get("eval_count") or 0),
    }


def local_loop(config: Config, once: bool = False) -> None:
    """The second line: questions for the local model, apart from the tasks, so a long task in
    a project never makes the conversation wait."""
    backoff = 5
    model = urllib.parse.quote(config.local_model or "")
    path = f"/device/llm/next?wait={LONG_POLL_SECONDS}&model={model}"
    while True:
        try:
            question = call(config, "GET", path)
            backoff = 5
            if question:
                answer = ask_local_model(config, question)
                call(config, "POST", f"/device/llm/{question['id']}/result", answer, timeout=60)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"Modelo local sem conexão ({exc}); tento de novo em {backoff}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
        if once:
            return


def genesis() -> None:
    """The Muninn in ASCII when the arm is started by hand in a terminal (under launchd there is
    no terminal, so the log stays clean). Missing player files just skip it."""
    if not sys.stdout.isatty():
        return
    here = Path(__file__).resolve().parent
    for folder in (here, here.parent / "brand/muninn"):
        if (folder / "muninn_ascii.py").is_file() and (folder / "muninn-ascii.json").is_file():
            sys.path.insert(0, str(folder))
            try:
                import muninn_ascii

                muninn_ascii.main([])
            except (ImportError, OSError, ValueError):
                pass
            finally:
                sys.path.remove(str(folder))
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
    if not args.once:
        genesis()
    print(f"Braço {VERSION} ligado a {config.server}; projetos: {', '.join(config.projects)}")
    if config.local_model and not args.once:
        print(f"Modelo local: {config.local_model} em {config.ollama}")
        threading.Thread(target=local_loop, args=(config,), daemon=True).start()
    loop(config, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
