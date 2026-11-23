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
import shlex
import signal
import subprocess
import sys
import tempfile
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
# 3: Bash inside Claude Code's sandbox, the whole process group ends with the task, a photo of
# the project before and after (changed files, undo), and "until the tests pass".
VERSION = "3"
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
# Every Bash command of a task runs in Claude Code's sandbox: writes only in the project and the
# temporary folder, no network, no retry outside it, and nothing runs if it cannot start. This
# is what bounds "edit + run the tests": a task can change a test and run it, but that code
# cannot reach the network or write outside the project. It also cannot read the keys below.
SECRETS = ["~/.ssh", "~/.aws", "~/.gnupg", "~/.config/visao", "~/Library/Keychains"]
SANDBOX = {
    "enabled": True,
    "failIfUnavailable": True,
    "allowUnsandboxedCommands": False,
    "network": {"allowedDomains": [], "strictAllowlist": True},
    "filesystem": {"denyRead": SECRETS},
}
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
    # The command that says whether a project's tests pass, per project (argv). Only projects
    # listed here accept "until the tests pass".
    tests: dict[str, list[str]] = field(default_factory=dict)
    test_attempts: int = 3
    test_timeout_minutes: int = 10

    @classmethod
    def load(cls, path: Path) -> Config:
        data = json.loads(path.read_text())
        projects, tests = {}, {}
        for name, entry in (data.get("projects") or {}).items():
            # "nome": "~/pasta", or "nome": {"pasta": "~/pasta", "testes": "make check"}
            if isinstance(entry, dict):
                folder, check = entry.get("pasta"), str(entry.get("testes") or "").strip()
            else:
                folder, check = entry, ""
            if not folder:
                raise ValueError(f"o projeto {name} precisa de pasta")
            projects[str(name)] = Path(str(folder)).expanduser().resolve()
            if check:
                tests[str(name)] = shlex.split(check)
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
            tests=tests,
            test_attempts=max(1, int(data.get("test_attempts", 3))),
            test_timeout_minutes=max(1, int(data.get("test_timeout_minutes", 10))),
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
        # (none here: dontAsk denies). It removes Bash unless --tools names it. --settings still
        # applies under --restricted: that is where the sandbox comes from.
        return [
            "--restricted",
            "--strict-mcp-config",
            "--tools",
            tools,
            "--settings",
            json.dumps({"sandbox": SANDBOX}),
        ]
    if _has(text, "--setting-sources") and _has(text, "--strict-mcp-config"):
        # Older Claude Code: your own settings only, no hooks, no MCP servers.
        flags = [
            "--setting-sources",
            "user",
            "--settings",
            json.dumps({"disableAllHooks": True, "sandbox": SANDBOX}),
            "--strict-mcp-config",
        ]
        return flags + (["--tools", tools] if _has(text, "--tools") else [])
    return None


def command(
    config: Config, task: dict, isolated: list[str], budget: float | None = None
) -> list[str]:
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
        str(round(config.max_budget_usd if budget is None else budget, 2)),
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


def _end_group(process: subprocess.Popen, sig: int = signal.SIGTERM) -> None:
    """Each task runs in its own process group: a dev server or watcher it left behind ends
    with it instead of living on in the Mac."""
    try:
        os.killpg(process.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _run_group(
    argv: list[str], folder: Path, env: dict[str, str], stdin: str, seconds: float
) -> tuple[int | None, str, str]:
    """Runs argv in a new process group. Returns (exit code, out, err); the code is None when
    it passed `seconds` and was stopped. Raises FileNotFoundError when argv[0] is missing.

    Output goes to files, not pipes: a process the task left in the background would hold a
    pipe open and keep us waiting until the timeout. When the main process ends, so does the
    rest of its group."""
    with (
        tempfile.TemporaryFile("w+") as given,
        tempfile.TemporaryFile("w+") as out_file,
        tempfile.TemporaryFile("w+") as err_file,
    ):
        given.write(stdin)
        given.seek(0)
        process = subprocess.Popen(  # noqa: S603 (fixed argv; the prompt goes on stdin)
            argv,
            cwd=folder,
            stdin=given,
            stdout=out_file,
            stderr=err_file,
            text=True,
            env=env,
            start_new_session=True,
        )
        code: int | None
        try:
            code = process.wait(timeout=max(1.0, seconds))
        except subprocess.TimeoutExpired:
            _end_group(process, signal.SIGINT)  # ends Claude's turn cleanly
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                _end_group(process, signal.SIGKILL)
                process.wait()
            code = None
        _end_group(process)
        time.sleep(0.05)
        _end_group(process, signal.SIGKILL)
        out_file.seek(0)
        err_file.seek(0)
        return code, out_file.read(), err_file.read()


def run_claude(
    config: Config,
    task: dict,
    folder: Path,
    isolated: list[str],
    budget: float | None = None,
    seconds: float | None = None,
) -> dict:
    """Runs one task and returns the body for /result. Never raises for a task failure."""
    limit = config.timeout_minutes * 60 if seconds is None else seconds
    try:
        code, out, err = _run_group(
            command(config, task, isolated, budget),
            folder,
            _environment(config),
            task["prompt"],
            limit,
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"Não achei o Claude Code ({config.claude}) neste Mac."}
    if code is None:
        return {
            "ok": False,
            "error": f"Passou de {config.timeout_minutes} min e eu interrompi.",
            "result": out[-MAX_RESULT:],
        }
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        detail = (err or out or "").strip()[-400:]
        return {"ok": False, "error": f"O Claude Code saiu com erro: {detail or code}"}
    failed = code != 0 or bool(data.get("is_error"))
    body = {
        "ok": not failed,
        "result": str(data.get("result") or "")[:MAX_RESULT],
        "session_id": data.get("session_id"),
        "cost_usd": data.get("total_cost_usd"),
    }
    if failed:
        body["error"] = str(data.get("subtype") or data.get("result") or "falhou")[:500]
    return body


# --- photos of the project: what a task changed, and how to undo it ------------------------
# A git of the arm's own, in ~/.config/visao/fotos/<projeto>.git, with the project as its work
# tree. The project's .git is never touched. Its .gitignore is respected: what it ignores
# (node_modules, .env) is neither listed nor undone.


class PhotoError(RuntimeError):
    pass


def _photo_git(config: Config, project: str, folder: Path, *args: str, timeout: int = 120) -> str:
    repo = config.state_dir / "fotos" / f"{project}.git"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_DIR=str(repo),
        GIT_WORK_TREE=str(folder),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_LITERAL_PATHSPECS="1",
        GIT_AUTHOR_NAME="Visão",
        GIT_AUTHOR_EMAIL="braco@visao.local",
        GIT_COMMITTER_NAME="Visão",
        GIT_COMMITTER_EMAIL="braco@visao.local",
    )
    if not (repo / "HEAD").is_file():
        repo.parent.mkdir(parents=True, exist_ok=True)
        _git_run(["git", "init", "-q"], folder, env, timeout)
    argv = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args]
    return _git_run(argv, folder, env, timeout)


def _git_run(argv: list[str], folder: Path, env: dict[str, str], timeout: int) -> str:
    try:
        done = subprocess.run(  # noqa: S603 (git with fixed arguments)
            argv, cwd=folder, env=env, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PhotoError(str(exc)) from exc
    if done.returncode != 0:
        raise PhotoError((done.stderr or done.stdout).strip()[-300:])
    return done.stdout


def photo(config: Config, project: str, folder: Path, label: str) -> str:
    """Records the project as it is now, under refs/visao/<label>. Returns the commit."""
    _photo_git(config, project, folder, "add", "-A", "--", ".")
    tree = _photo_git(config, project, folder, "write-tree").strip()
    commit = _photo_git(config, project, folder, "commit-tree", tree, "-m", label).strip()
    _photo_git(config, project, folder, "update-ref", f"refs/visao/{label}", commit)
    return commit


def _ref(config: Config, project: str, folder: Path, label: str) -> str | None:
    try:
        return _photo_git(config, project, folder, "rev-parse", "--verify", "-q", label).strip()
    except PhotoError:
        return None


def changed(config: Config, project: str, folder: Path, before: str, after: str) -> list[dict]:
    """The files that differ between two photos: A added, M changed, D deleted."""
    raw = _photo_git(
        config, project, folder, "diff", "--name-status", "--no-renames", "-z", before, after
    )
    parts = raw.split("\0")
    return [
        {"status": parts[i][:1], "path": parts[i + 1]}
        for i in range(0, len(parts) - 1, 2)
        if parts[i] and parts[i + 1]
    ]


def undo(config: Config, task: dict, folder: Path) -> dict:
    """Puts back the files an earlier task changed, without Claude. Refuses when one of them
    was changed again since: that is your work, and it is not mine to overwrite."""
    project, original = str(task.get("project", "")), str(task.get("undo_of") or "")
    try:
        before = _ref(config, project, folder, f"refs/visao/{original}/antes")
        after = _ref(config, project, folder, f"refs/visao/{original}/depois")
        if not original or before is None or after is None:
            return {"ok": False, "error": NO_PHOTO}
        touched = changed(config, project, folder, before, after)
        now = photo(config, project, folder, f"{task['id']}/agora")
        since = {c["path"] for c in changed(config, project, folder, after, now)}
        conflicts = sorted(c["path"] for c in touched if c["path"] in since)
        if conflicts:
            listed = ", ".join(conflicts[:10]) + ("…" if len(conflicts) > 10 else "")
            return {"ok": False, "error": f"{CHANGED_SINCE} {listed}"[:500]}
        root = folder.resolve()
        restore = [c["path"] for c in touched if c["status"] != "A"]
        for item in touched:
            if item["status"] == "A":
                target = (root / item["path"]).resolve()
                if target.is_relative_to(root) and target.is_file():
                    target.unlink()
        if restore:
            _photo_git(config, project, folder, "checkout", before, "--", *restore)
    except PhotoError as exc:
        return {"ok": False, "error": f"Não consegui desfazer: {exc}"[:500]}
    if not touched:
        return {"ok": True, "result": "A tarefa não tinha mudado nenhum arquivo.", "changed": []}
    return {
        "ok": True,
        "result": f"Voltei {len(touched)} arquivo(s) ao que eram antes da tarefa.",
        "changed": touched,
    }


NO_PHOTO = "Não tenho neste Mac a foto de antes dessa tarefa, então não mexi em nada."
CHANGED_SINCE = "Não desfiz: estes arquivos mudaram de novo depois da tarefa:"


# --- until the tests pass -------------------------------------------------------------------
# Whether they passed is the exit code of the command in braco.json, never what Claude says.


def sandboxed(argv: list[str], folder: Path) -> list[str] | None:
    """The tests run code a task may just have written: on the Mac they run in a sandbox with
    no network beyond this Mac and writes only in the project and the temporary folders. None
    where that is not available: then they do not run."""
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        return None
    writable = {
        os.path.realpath(folder),
        os.path.realpath(tempfile.gettempdir()),
        "/private/tmp",
        "/private/var/folders",
    }
    hidden = {os.path.realpath(os.path.expanduser(p)) for p in SECRETS}
    if any('"' in p or "\\" in p for p in writable | hidden):
        return None
    allow = " ".join(f'(subpath "{p}")' for p in sorted(writable))
    deny = " ".join(f'(subpath "{p}")' for p in sorted(hidden))
    profile = (
        "(version 1)(allow default)"
        '(deny network-outbound)(allow network-outbound (remote ip "localhost:*"))'
        f'(deny file-write*)(allow file-write* {allow} (subpath "/dev"))'
        f"(deny file-read* {deny})"
    )
    return ["/usr/bin/sandbox-exec", "-p", profile, *argv]


def run_tests(config: Config, project: str, folder: Path, seconds: float) -> dict:
    argv = config.tests[project]
    shown = shlex.join(argv)
    wrapped = sandboxed(argv, folder)
    if wrapped is None:
        return {"command": shown, "passed": False, "error": NO_TEST_SANDBOX}
    env = _environment(config)
    env.pop("ANTHROPIC_API_KEY", None)
    try:
        code, out, err = _run_group(wrapped, folder, env, "", seconds)
    except FileNotFoundError:
        return {"command": shown, "passed": False, "error": f"Não achei o comando {argv[0]}."}
    tail = (out + ("\n" if out and err else "") + err)[-TEST_TAIL:]
    if code is None:
        return {
            "command": shown,
            "passed": False,
            "tail": tail,
            "error": "Os testes passaram do tempo.",
        }
    if code != 0 and err.lstrip().startswith("sandbox-exec:"):
        return {
            "command": shown,
            "passed": False,
            "error": f"{NO_TEST_SANDBOX} ({err.strip()[:200]})",
        }
    return {"command": shown, "passed": code == 0, "tail": tail}


TEST_TAIL = 3000
NO_TEST_SANDBOX = "Não consegui isolar os testes neste Mac, então não rodei."
NO_TESTS = (
    "Você pediu até os testes passarem, mas o braco.json não diz como rodar os testes de "
    '{project}. Escreva "{project}": {{"pasta": "…", "testes": "make check"}} e peça de novo.'
)
RETRY = (
    "Os testes ainda não passam (`{command}`, tentativa {attempt} de {attempts}). Final da "
    "saída:\n\n{tail}\n\nCorrija o que falta para eles passarem, sem desligar nem pular testes."
)


def _cost(body: dict) -> float:
    try:
        return float(body.get("cost_usd") or 0)
    except (TypeError, ValueError):
        return 0.0


def until_tests_pass(config: Config, task: dict, folder: Path, isolated: list[str]) -> dict:
    """Claude works, the tests run, and while they fail Claude goes on in the same session:
    the same approval, the same budget and the same time limit for every attempt."""
    project = str(task["project"])
    started, limit = time.monotonic(), config.timeout_minutes * 60
    body = run_claude(config, task, folder, isolated, config.max_budget_usd, limit)
    spent, attempt, report = _cost(body), 0, None
    while body.get("ok"):
        attempt += 1
        left = limit - (time.monotonic() - started)
        report = run_tests(config, project, folder, min(config.test_timeout_minutes * 60, left))
        report["attempts"] = attempt
        budget = config.max_budget_usd - spent
        if report["passed"] or "error" in report:  # an error is not for Claude to fix
            break
        if attempt >= config.test_attempts or budget < 0.05 or left < 120:
            break
        if not body.get("session_id"):
            break
        follow = {
            **task,
            "resume_session": body["session_id"],
            "prompt": RETRY.format(
                command=report["command"],
                attempt=attempt,
                attempts=config.test_attempts,
                tail=report.get("tail", ""),
            ),
        }
        body = run_claude(config, follow, folder, isolated, budget, left)
        spent += _cost(body)
    body["cost_usd"] = round(spent, 6)
    if report is None:
        return body
    body["tests"] = report
    if not report["passed"] and body.get("ok"):
        body["ok"] = False
        body["error"] = report.get("error") or (
            f"Os testes (`{report['command']}`) não passaram depois de {attempt} tentativa(s)."
        )
    return body


def handle(config: Config, task: dict) -> dict:
    project = str(task.get("project", ""))
    folder = config.projects.get(project)
    if folder is None:
        names = ", ".join(sorted(config.projects)) or "nenhum"
        return {"ok": False, "error": f"Projeto não liberado neste Mac. Liberados: {names}."}
    if not folder.is_dir():
        return {"ok": False, "error": f"A pasta do projeto não existe: {folder}"}
    if task.get("kind") == "undo":
        return undo(config, task, folder)
    until = bool(task.get("until_tests"))
    if until and project not in config.tests:
        return {"ok": False, "error": NO_TESTS.format(project=project)}
    isolated = isolation(config)
    if isolated is None:
        missing = f"Não achei o Claude Code ({config.claude}) neste Mac."
        return {"ok": False, "error": TOO_OLD if _help(config.claude) else missing}
    task_id = str(task.get("id", ""))
    try:
        before = photo(config, project, folder, f"{task_id}/antes") if task_id else None
    except PhotoError as exc:
        print(f"Sem foto de antes ({exc}); a tarefa roda sem desfazer", file=sys.stderr)
        before = None
    if until:
        body = until_tests_pass(config, task, folder, isolated)
    else:
        body = run_claude(config, task, folder, isolated)
    if before is not None:
        try:
            after = photo(config, project, folder, f"{task_id}/depois")
            body["changed"] = changed(config, project, folder, before, after)[:MAX_CHANGED]
            body["snapshot"] = True
        except PhotoError as exc:
            print(f"Sem foto de depois ({exc})", file=sys.stderr)
    return body


MAX_CHANGED = 2000


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
