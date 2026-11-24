#!/usr/bin/env python3
"""O braço do Visão no Mac (docs/BRACO.md). Só biblioteca padrão: roda com o Python do sistema.

Busca no servidor tarefas que você aprovou, roda o Claude Code no projeto pedido (ou o executor
do próprio Visão, com qualquer modelo da corrente: "executor": "visao"), com uma lista fechada
de ferramentas, e devolve o resultado. Só faz requisições de saída: nenhuma porta aberta.

O que é permitido fica aqui no Mac, em ~/.config/visao/braco.json; o servidor não muda isso.
Uso: python3 visao_braco.py [--config caminho] [--once]
"""

# The system Python on macOS is 3.9: without this, `dict | None` in a signature fails at import.
from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
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
# 5: looks at the screen when the owner asks ("tela": true), on a line of its own.
# 4: the arm's own executor (ADR-0023): tools implemented here, the model asked step by step
# through the server, tests and git in a sandbox of the arm's own (bubblewrap on Linux too).
VERSION = "5"
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
    # docs/TELA.md: this computer lets the Visão look at its screen when the owner asks.
    screen: bool = False
    ollama: str = "http://127.0.0.1:11434"
    local_context: int = 16384
    # Where results wait until the server takes them, next to braco.json.
    state_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG.parent)
    # The command that says whether a project's tests pass, per project (argv). Only projects
    # listed here accept "until the tests pass".
    tests: dict[str, list[str]] = field(default_factory=dict)
    test_attempts: int = 3
    test_timeout_minutes: int = 10
    # Who codes (ADR-0023): "claude_code" (default) or "visao", for the Mac and per project.
    executor: str = "claude_code"
    executors: dict[str, str] = field(default_factory=dict)

    def executor_for(self, project: str) -> str:
        return self.executors.get(project, self.executor)

    @classmethod
    def load(cls, path: Path) -> Config:
        data = json.loads(path.read_text())
        projects, tests, executors = {}, {}, {}
        for name, entry in (data.get("projects") or {}).items():
            # "nome": "~/pasta", or "nome": {"pasta": "~/pasta", "testes": "make check"}
            if isinstance(entry, dict):
                folder, check = entry.get("pasta"), str(entry.get("testes") or "").strip()
                if entry.get("executor"):
                    executors[str(name)] = _executor(entry["executor"])
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
            screen=data.get("tela") is True,
            state_dir=path.expanduser().resolve().parent,
            tests=tests,
            test_attempts=max(1, int(data.get("test_attempts", 3))),
            test_timeout_minutes=max(1, int(data.get("test_timeout_minutes", 10))),
            executor=_executor(data.get("executor") or "claude_code"),
            executors=executors,
        )


EXECUTORS = ("claude_code", "visao")


def _executor(value: object) -> str:
    if value not in EXECUTORS:
        raise ValueError('executor precisa ser "claude_code" ou "visao"')
    return str(value)


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
    """What runs code a task may just have written (the tests, and git, which reads files the
    tests could have written) runs in a sandbox: no network beyond this Mac, writes only in the
    project and the temporary folders, never in .git, .claude, .mcp.json or CLAUDE.md (a hook
    planted there would run outside, later), and the key folders hidden. macOS: sandbox-exec.
    Linux: bubblewrap, without any network. None where neither exists: then nothing runs."""
    if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file():
        return _seatbelt(argv, folder)
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return _bubblewrap(argv, folder)
    return None


def _seatbelt(argv: list[str], folder: Path) -> list[str] | None:
    root = os.path.realpath(folder)
    writable = {
        root,
        os.path.realpath(tempfile.gettempdir()),
        "/private/tmp",
        "/private/var/folders",
    }
    hidden = {os.path.realpath(os.path.expanduser(p)) for p in SECRETS}
    if any('"' in p or "\\" in p for p in writable | hidden):
        return None
    allow = " ".join(f'(subpath "{p}")' for p in sorted(writable))
    deny = " ".join(f'(subpath "{p}")' for p in sorted(hidden))
    guarded = (
        f'(subpath "{root}/.git") (subpath "{root}/.claude") (literal "{root}/.mcp.json") '
        # macOS ignores case: claude.md is the same file.
        '(regex #"/[Cc][Ll][Aa][Uu][Dd][Ee](\\.[Ll][Oo][Cc][Aa][Ll])?\\.[Mm][Dd]$")'
    )
    # The last matching rule wins: the guarded paths stay read-only inside the project.
    profile = (
        "(version 1)(allow default)"
        '(deny network-outbound)(allow network-outbound (remote ip "localhost:*"))'
        f'(deny file-write*)(allow file-write* {allow} (subpath "/dev"))'
        f"(deny file-write* {guarded})"
        f"(deny file-read* {deny})"
    )
    return ["/usr/bin/sandbox-exec", "-p", profile, *argv]


def _bubblewrap(argv: list[str], folder: Path) -> list[str]:
    root = os.path.realpath(folder)
    temp = os.path.realpath(tempfile.gettempdir())
    args = [
        shutil.which("bwrap") or "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-net",
        "--unshare-pid",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
    ]  # fmt: skip
    for path in sorted({temp, "/tmp"}):  # noqa: S108 (writable inside the sandbox, as on the Mac)
        if os.path.isdir(path):
            args += ["--bind", path, path]
    args += ["--bind", root, root]
    # Only what exists can be mounted read-only; .git always exists in a repository.
    for name in (".git", ".claude", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md"):
        path = os.path.join(root, name)
        if os.path.lexists(path) and not os.path.islink(path):
            args += ["--ro-bind", path, path]
    for secret in sorted({os.path.realpath(os.path.expanduser(p)) for p in SECRETS}):
        if os.path.isdir(secret) and not root.startswith(secret + os.sep):
            args += ["--tmpfs", secret]
    return [*args, "--chdir", root, "--", *argv]


_SANDBOX_ERRORS = ("sandbox-exec:", "bwrap:")


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
    if code != 0 and err.lstrip().startswith(_SANDBOX_ERRORS):
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


# --- the arm's own executor (ADR-0023) -------------------------------------------------------
# The loop runs here and the head on the server: at each step the arm sends the server what
# happened so far and gets one action back. The model only picks among these tools; each one is
# implemented and checked here, whatever the model or the server says. No shell, no network.


class Refused(Exception):
    """A tool call the arm does not do. The reason goes back to the model."""


# Names and arguments the arm accepts, with their types. The server describes the same tools
# (core/arm/coder.py); this table is the one that decides.
VISAO_TOOLS: dict[str, dict[str, type]] = {
    "ler": {"caminho": str, "de_linha": int, "ate_linha": int},
    "listar": {"pasta": str},
    "buscar": {"texto": str, "pasta": str},
    "editar": {"caminho": str, "trecho": str, "novo": str},
    "criar": {"caminho": str, "conteudo": str},
    "rodar_testes": {},
    "git_status": {},
    "git_diff": {"caminho": str},
    "terminar": {"resumo": str},
}
VISAO_REQUIRED = {
    "ler": {"caminho"},
    "buscar": {"texto"},
    "editar": {"caminho", "trecho"},
    "criar": {"caminho", "conteudo"},
    "terminar": {"resumo"},
}
# Never read or written by the executor, a choice of the owner: what is read goes to the model's
# provider. The examples stay readable.
SECRET_FILES = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "id_dsa*",
    ".netrc",
    ".npmrc",
    ".pypirc",
)
SECRET_EXAMPLES = {".env.example", ".env.sample", ".env.template"}
# The same as PROTECTED, for paths: what would widen what the next tasks may do.
GUARDED_DIRS = {".git", ".claude"}
GUARDED_FILES = {"claude.md", "claude.local.md"}
SKIPPED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
}
MAX_OBSERVATION = 16_000
READ_LINES = 300
MAX_FILE_BYTES = 1_000_000
MAX_WRITE_CHARS = 200_000
MAX_LISTED = 400
MAX_FOUND = 100
STEP_TIMEOUT = 300
STEP_RETRIES = 3


def is_secret(name: str) -> bool:
    name = name.lower()
    return name not in SECRET_EXAMPLES and any(fnmatch.fnmatchcase(name, p) for p in SECRET_FILES)


def _guarded(parts: tuple[str, ...]) -> bool:
    lower = [p.lower() for p in parts]
    if any(p in GUARDED_DIRS for p in lower):
        return True
    return bool(lower) and (lower[-1] in GUARDED_FILES or lower == [".mcp.json"])


def inside(folder: Path, given: object, what: str = "caminho") -> Path:
    """The real path of `given` inside the project. Refuses absolute paths, `..` and symlinks
    that leave it, the guarded files and the secret ones, before anything is opened."""
    if not isinstance(given, str) or not given.strip() or "\0" in given:
        raise Refused(f"{what} vazio ou inválido")
    if given.startswith("~") or Path(given).is_absolute():
        raise Refused(f"{given} fica fora do projeto; use um caminho relativo à raiz dele")
    root = folder.resolve()
    target = (root / given).resolve()
    if target != root and not target.is_relative_to(root):
        raise Refused(f"{given} fica fora do projeto")
    real = target.relative_to(root).parts
    written = tuple(p for p in Path(given).parts if p not in ("", "."))
    if _guarded(real) or _guarded(written):
        raise Refused(f"{given} é protegido (.git, .claude, .mcp.json, CLAUDE.md)")
    if (real and is_secret(real[-1])) or (written and is_secret(written[-1])):
        raise Refused(f"{given} é arquivo de segredo; fica fora de alcance")
    return target


def _relative(folder: Path, path: Path) -> str:
    return path.relative_to(folder.resolve()).as_posix() or "."


def _text_of(path: Path) -> str:
    if not path.is_file():
        raise Refused(f"{path.name} não é um arquivo")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise Refused(f"{path.name} passa de 1 MB")
    raw = path.read_bytes()
    if b"\0" in raw[:8192]:
        raise Refused(f"{path.name} é binário")
    return raw.decode("utf-8", errors="replace")


def tool_read(folder: Path, args: dict) -> str:
    path = inside(folder, args["caminho"])
    lines = _text_of(path).splitlines()
    start = max(1, int(args.get("de_linha") or 1))
    end = min(len(lines), int(args.get("ate_linha") or start + READ_LINES - 1))
    end = min(end, start + READ_LINES - 1)
    shown, size = [], 0
    for number in range(start, end + 1):
        line = f"{number:>5}  {lines[number - 1]}"
        if size + len(line) > MAX_OBSERVATION - 200:
            end = number - 1
            break
        shown.append(line)
        size += len(line) + 1
    head = f"{_relative(folder, path)} ({len(lines)} linhas)"
    more = f"\n(continua: de_linha={end + 1})" if end < len(lines) else ""
    return head + "\n" + "\n".join(shown) + more


def _walk(start: Path):
    """Files and folders under start, without following symlinks or entering skipped folders."""
    for current, dirs, files in os.walk(start, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
        yield Path(current), dirs, sorted(files)


def _size_of(path: Path) -> str:
    """Lines of a text file, so the model knows what is big before opening it."""
    if is_secret(path.name):
        return " (segredo, fora de alcance)"
    try:
        if path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
            return ""
        raw = path.read_bytes()
    except OSError:
        return ""
    if b"\0" in raw[:8192]:
        return ""
    return f" ({raw.count(chr(10).encode())} linhas)"


def tool_list(folder: Path, args: dict) -> str:
    start = inside(folder, args.get("pasta") or ".", "pasta")
    if not start.is_dir():
        raise Refused(f"{args.get('pasta')} não é uma pasta")
    entries: list[str] = []
    for current, dirs, files in _walk(start):
        for name in dirs:
            entries.append(_relative(folder, current / name) + "/")
        for name in files:
            entries.append(_relative(folder, current / name) + _size_of(current / name))
        if len(entries) >= MAX_LISTED:
            break
    cut = len(entries) > MAX_LISTED
    listed = "\n".join(sorted(entries[:MAX_LISTED])) or "(vazia)"
    return listed + ("\n(mais itens; liste uma subpasta)" if cut else "")


def tool_search(folder: Path, args: dict) -> str:
    wanted = args["texto"]
    if not wanted.strip():
        raise Refused("texto vazio")
    start = inside(folder, args.get("pasta") or ".", "pasta")
    needle, found = wanted.lower(), []
    for current, _, files in _walk(start):
        for name in files:
            path = current / name
            if is_secret(name) or path.is_symlink():
                continue
            try:
                text = _text_of(path)
            except (Refused, OSError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if needle in line.lower():
                    found.append(f"{_relative(folder, path)}:{number}: {line.strip()[:200]}")
                    if len(found) >= MAX_FOUND:
                        return "\n".join(found) + f"\n(parei em {MAX_FOUND} resultados)"
    return "\n".join(found) or "Nada encontrado."


def _save_text(path: Path, text: str) -> None:
    partial = path.with_name(f".{path.name}.visao-tmp")
    partial.write_text(text, encoding="utf-8")
    if path.exists():
        os.chmod(partial, path.stat().st_mode & 0o7777)
    os.replace(partial, path)


# Where cheap models fail most (docs/research: Goose, OpenClaw, Hermes): a snippet copied with a
# trailing space, a different indentation or curly quotes. Each failed edit costs a whole step,
# so an exact match comes first, then these, in order, and only a single match is ever applied.
_LOOKALIKES = str.maketrans(
    {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "\u00a0": " "}
)


def _plain(line: str) -> str:
    return unicodedata.normalize("NFKC", line).translate(_LOOKALIKES).rstrip()


_LOOSE = (
    ("sem espaço no fim", lambda line: line.rstrip()),
    ("aspas e traços normalizados", _plain),
    ("recuo diferente", lambda line: _plain(line).strip()),
)


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _loose_match(lines: list[str], old: list[str], new: str) -> tuple[str, int, list[str]] | None:
    """(how, first line, the file's lines with the snippet replaced) for the first loose way
    that finds the snippet exactly once."""
    size = len(old)
    for how, norm in _LOOSE:
        wanted = [norm(line) for line in old]
        found = [
            i
            for i in range(len(lines) - size + 1)
            if [norm(line) for line in lines[i : i + size]] == wanted
        ]
        if len(found) != 1:
            continue
        i = found[0]
        replacement = new.split("\n") if new else []
        if how == "recuo diferente" and old and replacement:
            # The model's indentation was off by a constant: shift the new lines the same way.
            have, gave = _indent(lines[i]), _indent(old[0])
            replacement = [
                have + line[len(gave) :] if line.startswith(gave) else line for line in replacement
            ]
        return how, i + 1, lines[:i] + replacement + lines[i + size :]
    return None


def _numbered(lines: list[str], center: int, around: int = 10) -> str:
    start, end = max(0, center - around), min(len(lines), center + around)
    return "\n".join(f"{n + 1:>5}  {lines[n]}" for n in range(start, end))


def _closest(lines: list[str], old: str) -> str:
    """ "Você quis dizer": the line most like the snippet's first one, with 20 lines around."""
    first = next((line for line in old.splitlines() if line.strip()), old).strip()
    best, score = 0, 0.0
    for n, line in enumerate(lines):
        ratio = difflib.SequenceMatcher(None, first, line.strip()).ratio()
        if ratio > score:
            best, score = n, ratio
    if score < 0.5:
        return ""
    return f" O mais parecido está perto da linha {best + 1}:\n{_numbered(lines, best)}"


def _diff(before: str, after: str, name: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(), f"a/{name}", f"b/{name}", n=2, lineterm=""
    )
    return "\n".join(lines)[:4000]


def tool_edit(folder: Path, args: dict) -> str:
    path = inside(folder, args["caminho"])
    old, new = args["trecho"], args.get("novo", "")
    if not old:
        raise Refused("trecho vazio")
    if len(new) > MAX_WRITE_CHARS:
        raise Refused("o trecho novo é grande demais")
    if not path.is_file():
        raise Refused(f"{args['caminho']} não existe; para um arquivo novo, use criar")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise Refused(f"{args['caminho']} não é texto UTF-8") from exc
    name, lines = _relative(folder, path), text.split("\n")
    count, how = text.count(old), ""
    if count > 1:
        where = [str(text[: m.start()].count("\n") + 1) for m in re.finditer(re.escape(old), text)]
        raise Refused(
            f"o trecho aparece {count} vezes (linhas {', '.join(where[:10])}); inclua mais "
            "linhas em volta para ficar único"
        )
    if count == 1:
        after = text.replace(old, new, 1)
        first = text[: text.index(old)].count("\n") + 1
    else:
        loose = _loose_match(lines, old.strip("\n").split("\n"), new.strip("\n"))
        if loose is None:
            raise Refused(
                "o trecho não está no arquivo."
                + _closest(lines, old)
                + (" Leia de novo e copie exatamente; o arquivo pode ter mudado.")
            )
        how, first, changed_lines = loose
        after = "\n".join(changed_lines)
    _save_text(path, after)
    note = f" (achei com {how})" if how else ""
    return f"Editei {name}{note}, a partir da linha {first}.\n{_diff(text, after, name)}"


def tool_create(folder: Path, args: dict) -> str:
    path = inside(folder, args["caminho"])
    content = args["conteudo"]
    if len(content) > MAX_WRITE_CHARS:
        raise Refused("o conteúdo é grande demais")
    if path.exists() or path.is_symlink():
        raise Refused(f"{args['caminho']} já existe; para mudar, use editar")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.parent.resolve().is_relative_to(folder.resolve()):
        raise Refused(f"{args['caminho']} fica fora do projeto")
    with open(path, "x", encoding="utf-8") as handle:
        handle.write(content)
    return f"Criei {_relative(folder, path)}."


# Git reads config and attributes the tests could have written: hooks, fsmonitor, external diff
# and textconv off, and it runs in the sandbox like the tests. Secret files never show.
GIT = [
    "git",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.pager=cat",
    "--no-pager",
    "--no-optional-locks",
]
NOT_SECRETS = [f":(exclude,glob,icase)**/{p}" for p in SECRET_FILES]


def tool_git(config: Config, folder: Path, which: str, args: dict, seconds: float) -> str:
    if which == "status":
        argv = [*GIT, "status", "--short", "--untracked-files=all"]
    else:
        target = _relative(folder, inside(folder, args["caminho"])) if args.get("caminho") else "."
        argv = [*GIT, "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--", target]
        argv += NOT_SECRETS
    wrapped = sandboxed(argv, folder)
    if wrapped is None:
        raise Refused("não consegui isolar o git neste computador, então não rodei")
    env = _environment(config)
    env.pop("ANTHROPIC_API_KEY", None)
    code, out, err = _run_group(wrapped, folder, env, "", max(5.0, min(60.0, seconds)))
    if code is None:
        raise Refused("o git passou do tempo")
    if code != 0:
        raise Refused(f"o git saiu com erro: {(err or out).strip()[-500:]}")
    return out.strip() or "(nada)"


def tool_tests(config: Config, project: str, folder: Path, seconds: float) -> tuple[bool, str]:
    report = run_tests(config, project, folder, seconds)
    if "error" in report:
        return False, report["error"]
    verdict = "Passaram." if report["passed"] else "Não passaram."
    return report["passed"], f"`{report['command']}`: {verdict}\n\n{report.get('tail', '')}"


def check_args(tool: str, args: object) -> str | None:
    if not isinstance(args, dict):
        return "args precisa ser um objeto"
    accepted = VISAO_TOOLS[tool]
    for name, value in args.items():
        if name not in accepted:
            return f"{tool} não aceita {name}"
        kind = accepted[name]
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            return f"{name} precisa ser {'texto' if kind is str else 'número'}"
    missing = sorted(VISAO_REQUIRED.get(tool, set()) - set(args))
    return f"falta {', '.join(missing)}" if missing else None


def execute(
    config: Config,
    project: str,
    folder: Path,
    tool: object,
    args: object,
    allowed: list[str],
    seconds: float,
) -> tuple[bool, str]:
    """Runs one tool call. Never raises: a refusal or an error is the observation."""
    if not isinstance(tool, str) or tool not in allowed or tool not in VISAO_TOOLS:
        listed = ", ".join(allowed)
        return False, f"Recusado: {tool!r} não é uma ferramenta liberada neste Mac ({listed})."
    problem = check_args(tool, args)
    if problem:
        return False, f"Recusado: {problem}."
    assert isinstance(args, dict)
    try:
        if tool == "ler":
            text = tool_read(folder, args)
        elif tool == "listar":
            text = tool_list(folder, args)
        elif tool == "buscar":
            text = tool_search(folder, args)
        elif tool == "editar":
            text = tool_edit(folder, args)
        elif tool == "criar":
            text = tool_create(folder, args)
        elif tool == "rodar_testes":
            return tool_tests(config, project, folder, seconds)
        elif tool in ("git_status", "git_diff"):
            text = tool_git(config, folder, tool[4:], args, seconds)
        else:
            return False, f"Recusado: {tool} não se executa."
    except Refused as exc:
        return False, f"Recusado: {exc}."
    except (OSError, UnicodeError, ValueError) as exc:
        return False, f"Erro: {exc}"[:2000]
    return True, text


class StepFailed(RuntimeError):
    pass


def ask_step(config: Config, task_id: str, tools: list[str], steps: list[dict]) -> dict:
    """The next action from the server. Retries a dropped connection; a task the server no
    longer has with this Mac ends here."""
    body = {
        "tools": tools,
        "steps": steps[-200:],
        "max_steps": config.max_turns,
        "max_usd": round(config.max_budget_usd, 2),
    }
    for attempt in range(STEP_RETRIES):
        try:
            reply = call(config, "POST", f"/device/tasks/{task_id}/step", body, STEP_TIMEOUT)
            return reply if isinstance(reply, dict) else {}
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 409, 401):
                raise StepFailed("O servidor não está mais com essa tarefa neste Mac.") from exc
            if exc.code < 500 or attempt == STEP_RETRIES - 1:
                raise StepFailed(f"O servidor recusou o passo ({exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == STEP_RETRIES - 1:
                raise StepFailed(f"Perdi a conexão com o servidor no meio ({exc}).") from exc
        time.sleep(5 * (attempt + 1))
    raise StepFailed("O servidor não respondeu.")


def _entry(tool: str | None, args: dict, note: object, ok: bool, result: str) -> dict:
    return {
        "tool": tool,
        "args": args if tool else {},
        "note": str(note or "")[:4000],
        "ok": ok,
        "result": result[:MAX_OBSERVATION],
    }


MAX_NUDGES = 2
NO_PROOF = (
    "Você mudou {files} e não rodou os testes depois disso. Rode rodar_testes antes de "
    "terminar. Se não der para rodar, termine de novo e diga por quê; não diga que funciona "
    "sem o resultado dos testes."
)


def run_visao(config: Config, task: dict, folder: Path) -> dict:
    """The arm's own executor. Ends at `terminar`, at the limits of steps and time of braco.json,
    or when the server says stop (its limits of steps and cost, no provider). With "until the
    tests pass", `terminar` runs the tests, and while they fail the loop goes on."""
    project, task_id = str(task["project"]), str(task["id"])
    until = bool(task.get("until_tests"))
    tools = [t for t in VISAO_TOOLS if t != "rodar_testes" or project in config.tests]
    started, limit = time.monotonic(), config.timeout_minutes * 60
    steps: list[dict] = []
    cost, attempts, report = 0.0, 0, None
    nudges, unproven = 0, []  # files changed since the tests last ran

    def end(ok: bool, result: str = "", error: str = "") -> dict:
        body: dict = {"ok": ok, "result": result[:MAX_RESULT], "cost_usd": round(cost, 6)}
        body["executor"] = "visao"
        if error:
            body["error"] = error[:500]
        if report is not None:
            body["tests"] = report
        return body

    while True:
        left = limit - (time.monotonic() - started)
        if left <= 0:
            return end(False, error=f"Passou de {config.timeout_minutes} min e eu parei.")
        if len(steps) >= config.max_turns:
            return end(False, error=f"Cheguei ao limite de {config.max_turns} passos e parei.")
        try:
            reply = ask_step(config, task_id, tools, steps)
        except StepFailed as exc:
            return end(False, error=str(exc))
        try:
            cost = float(reply.get("cost_usd") or cost)
        except (TypeError, ValueError):
            pass
        if reply.get("stop"):
            return end(False, error=str(reply["stop"]))
        action = reply.get("action")
        if not isinstance(action, dict):
            reason = str(reply.get("invalid") or "a resposta não trouxe uma ação")
            steps.append(_entry(None, {}, reply.get("note"), False, reason))
            continue
        tool, args = action.get("tool"), action.get("args") or {}
        if tool == "terminar" and check_args("terminar", args) is None:
            summary = str(args["resumo"]).strip() or "Terminei, sem nada a relatar."
            if not until and unproven and "rodar_testes" in tools and nudges < MAX_NUDGES:
                # No proof, no end (Hermes): it changed files and never ran the tests since.
                nudges += 1
                files = ", ".join(sorted(set(unproven))[:10])
                steps.append(
                    _entry("terminar", args, reply.get("note"), False, NO_PROOF.format(files=files))
                )
                continue
            if not until:
                return end(True, summary)
            attempts += 1
            seconds = min(config.test_timeout_minutes * 60, max(1.0, left))
            report = run_tests(config, project, folder, seconds)
            report["attempts"] = attempts
            if report["passed"]:
                return end(True, summary)
            if "error" in report or attempts >= config.test_attempts or left < 120:
                failed = report.get("error") or (
                    f"Os testes (`{report['command']}`) não passaram depois de "
                    f"{attempts} tentativa(s)."
                )
                return end(False, summary, failed)
            retry = RETRY.format(
                command=report["command"],
                attempt=attempts,
                attempts=config.test_attempts,
                tail=report.get("tail", ""),
            )
            steps.append(_entry("terminar", args, reply.get("note"), False, retry))
            continue
        ok, result = execute(config, project, folder, tool, args, tools, left)
        if tool == "rodar_testes":
            unproven = []
        elif ok and tool in ("editar", "criar") and isinstance(args, dict):
            unproven.append(str(args.get("caminho")))
        steps.append(
            _entry(str(tool), args if isinstance(args, dict) else {}, reply.get("note"), ok, result)
        )


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
    visao = config.executor_for(project) == "visao"
    isolated: list[str] = []
    if not visao:
        found = isolation(config)
        if found is None:
            missing = f"Não achei o Claude Code ({config.claude}) neste Mac."
            return {"ok": False, "error": TOO_OLD if _help(config.claude) else missing}
        isolated = found
    task_id = str(task.get("id", ""))
    try:
        before = photo(config, project, folder, f"{task_id}/antes") if task_id else None
    except PhotoError as exc:
        print(f"Sem foto de antes ({exc}); a tarefa roda sem desfazer", file=sys.stderr)
        before = None
    if visao:
        body = run_visao(config, task, folder)
    elif until:
        body = until_tests_pass(config, task, folder, isolated)
    else:
        body = run_claude(config, task, folder, isolated)
    body.setdefault("executor", "claude_code")
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


# --- the screen (docs/TELA.md) --------------------------------------------------------------
# Only with "tela": true in braco.json. The server asks only when the owner's own message asked
# to see the screen; the arm captures the monitor under the mouse (the one being looked at),
# shrinks it to what a model reads (1568 px) and says so on the screen itself.

SCREEN_SIDE = 1568
SCREEN_MAX_BYTES = 4_500_000
_MONITOR = re.compile(r"(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)")


def _output(argv: list[str], seconds: float = 10) -> str:
    try:
        done = subprocess.run(  # noqa: S603 (fixed argv)
            argv, capture_output=True, text=True, timeout=seconds
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout if done.returncode == 0 else ""


def monitor_under_mouse() -> tuple[int, int, int, int] | None:
    """(width, height, x, y) of the X11 monitor the mouse is on, or None (one monitor, or no
    xrandr/xdotool): then the whole screen."""
    mouse = dict(
        line.split("=", 1)
        for line in _output(["xdotool", "getmouselocation", "--shell"]).split()
        if "=" in line
    )
    try:
        mx, my = int(mouse["X"]), int(mouse["Y"])
    except (KeyError, ValueError):
        return None
    for match in _MONITOR.finditer(_output(["xrandr", "--listactivemonitors"])):
        w, h, x, y = (int(v) for v in match.groups())
        if x <= mx < x + w and y <= my < y + h:
            return w, h, x, y
    return None


def capture_command(target: Path) -> list[list[str]] | None:
    """The commands that leave a JPEG of at most 1568 px at `target`, for this system."""
    if sys.platform == "darwin":
        return [
            ["/usr/sbin/screencapture", "-x", "-m", "-t", "jpg", str(target)],
            ["/usr/bin/sips", "-Z", str(SCREEN_SIDE), str(target)],
        ]
    if sys.platform.startswith("linux") and os.environ.get("DISPLAY") and shutil.which("import"):
        crop = []
        monitor = monitor_under_mouse()
        if monitor is not None:
            w, h, x, y = monitor
            crop = ["-crop", f"{w}x{h}+{x}+{y}", "+repage"]
        resize = ["-resize", f"{SCREEN_SIDE}x{SCREEN_SIDE}>", "-quality", "80"]
        return [["import", "-silent", "-window", "root", *crop, *resize, f"jpg:{target}"]]
    return None


def _tell_screen(text: str) -> None:
    """A notice on this computer: the owner always knows when the screen was taken."""
    if sys.platform == "darwin":
        script = f'display notification "{text}" with title "Visão"'
        _output(["/usr/bin/osascript", "-e", script])
    elif shutil.which("notify-send"):
        _output(["notify-send", "-a", "Visão", "Visão", text])


def capture_screen() -> dict:
    """Never raises: {"ok", "media_type", "data"} with the JPEG in base64, or {"ok": False}."""
    import base64

    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "tela.jpg"
        steps = capture_command(target)
        if steps is None:
            return {"ok": False, "error": NO_SCREEN}
        for argv in steps:
            try:
                done = subprocess.run(  # noqa: S603 (fixed argv)
                    argv, capture_output=True, text=True, timeout=30
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {"ok": False, "error": f"A captura falhou ({exc})."}
            if done.returncode != 0:
                detail = (done.stderr or done.stdout).strip()[-200:]
                return {"ok": False, "error": f"A captura falhou: {detail or done.returncode}"}
        try:
            raw = target.read_bytes()
        except OSError:
            return {"ok": False, "error": SCREEN_DENIED}
    if not raw.startswith(b"\xff\xd8") or len(raw) > SCREEN_MAX_BYTES:
        return {"ok": False, "error": SCREEN_DENIED}
    _tell_screen("Olhei sua tela agora, como você pediu.")
    return {"ok": True, "media_type": "image/jpeg", "data": base64.b64encode(raw).decode()}


NO_SCREEN = (
    "Este computador não tem como capturar a tela (no Linux preciso do ImageMagick e de uma "
    "sessão X11; no Mac, do screencapture)."
)
SCREEN_DENIED = (
    "A captura não saiu. No Mac, libere Gravação de Tela para o Python em Ajustes do Sistema > "
    "Privacidade e Segurança."
)


def screen_loop(config: Config, once: bool = False) -> None:
    """The third line: requests to look at the screen, apart from the tasks, so a long task
    never makes the owner wait for a look."""
    backoff = 5
    while True:
        try:
            request = call(config, "GET", f"/device/screen/next?wait={LONG_POLL_SECONDS}")
            backoff = 5
            if request:
                answer = capture_screen()
                call(config, "POST", f"/device/screen/{request['id']}/result", answer, timeout=60)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"Tela sem conexão ({exc}); tento de novo em {backoff}s", file=sys.stderr)
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
    if config.screen and not args.once:
        print('Tela: olho quando você pede ("tela": true)')
        threading.Thread(target=screen_loop, args=(config,), daemon=True).start()
    loop(config, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
