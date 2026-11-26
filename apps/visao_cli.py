"""`visao`: run the Visão on the owner's machine (docs/research/execucao_local.md, etapa 3).

    visao iniciar [--porta 8000] [--fundo]
    visao parar
    visao estado
    visao servico instalar [--porta 8000] | remover
    visao conta criar --email voce@exemplo.com

One process on 127.0.0.1: the API with the worker inside it (VISION_WORKER_IN_API) and the web
app on the same address (VISION_WEB_DIR), with SQLite migrated on start. It runs from the code's
folder, where `.env` and the migrations live. What it needs to find itself again (the process,
the port, the log) goes in ~/.visao (VISAO_HOME). The arm on the Mac and the server stay as they
are; this is only the local way to run the same code.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from apps import visao_servico as servico

# Inside the Mac app the code is frozen (PyInstaller, docs/APP_MAC.md): its files are in the app's
# folder, read-only, and the configuration lives in ~/.visao instead of beside the code.
FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "apps" / "web" / "dist"
DEFAULT_PORT = 8000
# The first start makes the database (41 migrations: 15 s here, more on a Mac checking every
# library the first time); a process that dies is seen at once, not after this.
START_WAIT_SECONDS = 120.0
STOP_WAIT_SECONDS = 25.0


def home() -> Path:
    return Path(os.environ.get("VISAO_HOME", "~/.visao")).expanduser()


def state_file() -> Path:
    return home() / "visao.json"


def log_file() -> Path:
    return home() / "visao.log"


def self_command() -> list[str]:
    """How this command runs itself again (in the background, or as the system's service)."""
    return [sys.executable] if FROZEN else [sys.executable, "-m", "apps.visao_cli"]


def criar_config(example: Path, target: Path, database: Path) -> None:
    """A .env of its own: the example, with a new secret key and the database in `database`."""
    import secrets

    lines = []
    for line in example.read_text(encoding="utf-8").splitlines():
        if line.startswith("VISION_SECRET_KEY="):
            line = "VISION_SECRET_KEY=" + secrets.token_urlsafe(48)
        elif line.startswith("VISION_DATABASE_URL="):
            line = "VISION_DATABASE_URL=sqlite:///" + str(database)
        lines.append(line)
    target.parent.mkdir(parents=True, exist_ok=True)
    database.parent.mkdir(parents=True, exist_ok=True)
    database.parent.chmod(0o700)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target.chmod(0o600)


def _frozen_config(environ: dict[str, str]) -> None:
    """The app keeps its .env in ~/.visao, made on the first start."""
    env_file = Path(environ.setdefault("VISION_ENV_FILE", str(home() / ".env")))
    if not env_file.exists():
        home().mkdir(parents=True, exist_ok=True)
        home().chmod(0o700)
        criar_config(ROOT / ".env.example", env_file, home() / "dados" / "visao.db")


def read_state() -> dict | None:
    try:
        return json.loads(state_file().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_state(pid: int, port: int) -> None:
    home().mkdir(parents=True, exist_ok=True)
    state_file().write_text(
        json.dumps({"pid": pid, "port": port, "started_at": datetime.now(UTC).isoformat()})
    )


def clear_state(pid: int | None = None) -> None:
    """Removes the state, but only this process's (a newer start may have replaced it)."""
    current = read_state()
    if current is None or pid is None or current.get("pid") == pid:
        state_file().unlink(missing_ok=True)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def running() -> dict | None:
    """The state of a Visão that is running, or None (a stale state file is cleaned up)."""
    current = read_state()
    if current is None:
        return None
    if not alive(int(current.get("pid", 0))):
        clear_state()
        return None
    return current


def get_json(port: int, path: str, timeout: float = 2.0) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as reply:  # noqa: S310
            return reply.status, json.loads(reply.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return 0, None


def _prepare(environ: dict[str, str]) -> tuple[str, bool]:
    """Points the app at this machine's way of running, migrates SQLite. Returns the database
    URL and whether the worker runs here."""
    os.chdir(ROOT)
    environ.setdefault("VISION_WEB_DIR", str(WEB_DIR))
    from apps.api.settings import get_settings

    settings = get_settings()
    local = settings.database_url.startswith("sqlite")
    # A shared PostgreSQL already has its worker on the server: two would think and speak twice
    # (scripts/dev.sh). VISAO_LOCAL_WORKER=1 overrides it on purpose.
    worker = local or environ.get("VISAO_LOCAL_WORKER") == "1"
    environ["VISION_WORKER_IN_API"] = "1" if worker else "0"
    if local:
        # On this machine only: the first account can be made on the screen (ADR-0027).
        environ.setdefault("VISION_FIRST_RUN_SETUP", "1")
    get_settings.cache_clear()
    if local:
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    return settings.database_url, worker


def iniciar(port: int, fundo: bool) -> int:
    current = running()
    if current is not None:
        print(f"O Visão já está rodando (processo {current['pid']}, porta {current['port']}).")
        return 0
    if not (WEB_DIR / "index.html").is_file():
        print(
            "Falta o build do web. Rode uma vez: npm --prefix apps/web ci && "
            "npm --prefix apps/web run build",
            file=sys.stderr,
        )
        return 1
    # Installed as a service: the system starts it (a process of our own would only fight the
    # service for the port). The service itself runs this command with VISAO_SERVICO=1.
    if servico.installed() and os.environ.get("VISAO_SERVICO") != "1":
        if servico.start() != 0:
            print("O serviço não ligou.", file=sys.stderr)
            return 1
        return _wait_up(port, lambda: False, "pelo serviço")
    if fundo:
        return _iniciar_no_fundo(port)

    _, worker = _prepare(os.environ)
    if os.environ.get("VISAO_PARENT_WATCH") == "1":
        watch_parent()
    write_state(os.getpid(), port)
    note = "" if worker else " (sem o worker: banco compartilhado)"
    print(f"Visão em http://127.0.0.1:{port}{note}")
    import uvicorn

    try:
        uvicorn.run("apps.api.main:app", host="127.0.0.1", port=port, workers=1, log_level="info")
    finally:
        clear_state(os.getpid())
    return 0


def watch_parent(every: float = 2.0) -> None:
    """The Mac app's server stops when the app is gone. The app stops it on a normal quit, but
    killed (Force Quit, a crash) it left the server running with the old settings, and the next
    app found it on the port and used it (25/11/2026). Only the app sets VISAO_PARENT_WATCH: the
    service and `iniciar --fundo` have no parent on purpose."""
    import threading

    parent = os.getppid()
    if parent <= 1:
        return

    def watch() -> None:
        while os.getppid() == parent:
            time.sleep(every)
        print("O app que abriu o servidor fechou; desligando.", flush=True)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=watch, name="visao-parent-watch", daemon=True).start()


def _iniciar_no_fundo(port: int) -> int:
    home().mkdir(parents=True, exist_ok=True)
    with log_file().open("ab") as log:
        child = subprocess.Popen(  # noqa: S603
            [*self_command(), "iniciar", "--porta", str(port)],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return _wait_up(port, lambda: child.poll() is not None, f"processo {child.pid}")


def _wait_up(port: int, died, how: str) -> int:
    deadline = time.monotonic() + START_WAIT_SECONDS
    while time.monotonic() < deadline:
        if died():
            print(f"O Visão não subiu. Veja o log: {log_file()}", file=sys.stderr)
            return 1
        status, _ = get_json(port, "/api/health", timeout=1.0)
        if status == 200:
            print(f"Visão em http://127.0.0.1:{port} ({how}, log em {log_file()})")
            return 0
        time.sleep(0.5)
    print(f"O Visão demorou para responder. Veja o log: {log_file()}", file=sys.stderr)
    return 1


def parar() -> int:
    current = running()
    if current is None:
        print("O Visão não está rodando.")
        return 0
    pid = int(current["pid"])
    if servico.installed():
        # The service manager would start it again after a plain SIGTERM.
        servico.stop()
    else:
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while time.monotonic() < deadline and alive(pid):
        time.sleep(0.2)
    if alive(pid):
        print(f"O processo {pid} ainda está terminando um trabalho; tente de novo em instantes.")
        return 1
    clear_state(pid)
    print("Visão parado.")
    return 0


def _heartbeat_age() -> float | None:
    from apps.worker.health import HEARTBEAT

    try:
        return time.time() - HEARTBEAT.stat().st_mtime
    except FileNotFoundError:
        return None


def _database_label(url: str) -> str:
    if url.startswith("sqlite"):
        return url.split("///", 1)[-1] or "memória"
    return url.split("@")[-1]  # never the user and password


def _service_line() -> str:
    if servico.kind() is None:
        return "Serviço: não disponível neste sistema"
    return f"Serviço: {'instalado' if servico.installed() else 'não instalado'} ({servico.kind()})"


def estado() -> int:
    current = running()
    if current is None:
        print(f"Parado.\n{_service_line()}")
        return 1
    port = int(current["port"])
    status, _ = get_json(port, "/api/health")
    _, ready = get_json(port, "/api/ready")
    _, release = get_json(port, "/api/release")
    os.chdir(ROOT)
    from apps.api.settings import get_settings

    settings = get_settings()
    lines = [
        f"Rodando: processo {current['pid']}, http://127.0.0.1:{port}",
        f"Responde: {'sim' if status == 200 else 'não'}",
        f"Banco: {(ready or {}).get('database', 'desconhecido')} "
        f"({_database_label(settings.database_url)})",
        f"Versão: {(release or {}).get('revision', 'desconhecida')}",
    ]
    age = _heartbeat_age()
    lines.append("Worker: sem sinal ainda" if age is None else f"Worker: sinal há {age:.0f} s")
    lines.append(_service_line())
    print("\n".join(lines))
    return 0 if status == 200 else 1


def conta_criar(email: str) -> int:
    """The first user (the password is asked in the terminal) and the agent's genesis."""
    os.chdir(ROOT)
    from apps.api import cli as account

    code = account.main(["create-user", "--email", email])
    if code == 0:
        code = account.main(["genesis"])
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="visao", description="O Visão na sua máquina.")
    sub = parser.add_subparsers(dest="comando", required=True)
    start = sub.add_parser("iniciar", help="sobe o Visão em 127.0.0.1, com o worker e o site")
    start.add_argument("--porta", type=int, default=DEFAULT_PORT)
    start.add_argument("--fundo", action="store_true", help="roda em segundo plano, com log")
    sub.add_parser("parar", help="desliga o Visão que está rodando")
    sub.add_parser("estado", help="diz se está rodando, se responde e o último sinal do worker")
    service = sub.add_parser("servico", help="sobe com o login e volta sozinho se cair")
    service_sub = service.add_subparsers(dest="acao", required=True)
    install = service_sub.add_parser("instalar", help="launchd no macOS, systemd no Linux")
    install.add_argument("--porta", type=int, default=DEFAULT_PORT)
    service_sub.add_parser("remover", help="desliga e apaga o serviço")
    account = sub.add_parser("conta", help="cria o primeiro usuário")
    account_sub = account.add_subparsers(dest="acao", required=True)
    create = account_sub.add_parser("criar", help="pede a senha no terminal e faz a gênese")
    create.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if FROZEN:
        _frozen_config(os.environ)
    if args.comando == "servico":
        if args.acao == "instalar":
            return servico.instalar(ROOT, args.porta, home(), log_file())
        return servico.remover()
    if args.comando == "conta":
        return conta_criar(args.email)
    if args.comando == "iniciar":
        return iniciar(args.porta, args.fundo)
    if args.comando == "parar":
        return parar()
    return estado()


if __name__ == "__main__":
    raise SystemExit(main())
