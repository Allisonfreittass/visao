"""`visao`: run the Visão on the owner's machine (docs/research/execucao_local.md, etapa 3).

    visao iniciar [--porta 8000] [--fundo]
    visao parar
    visao estado

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

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "apps" / "web" / "dist"
DEFAULT_PORT = 8000
START_WAIT_SECONDS = 30.0
STOP_WAIT_SECONDS = 25.0


def home() -> Path:
    return Path(os.environ.get("VISAO_HOME", "~/.visao")).expanduser()


def state_file() -> Path:
    return home() / "visao.json"


def log_file() -> Path:
    return home() / "visao.log"


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
    if fundo:
        return _iniciar_no_fundo(port)

    _, worker = _prepare(os.environ)
    write_state(os.getpid(), port)
    note = "" if worker else " (sem o worker: banco compartilhado)"
    print(f"Visão em http://127.0.0.1:{port}{note}")
    import uvicorn

    try:
        uvicorn.run("apps.api.main:app", host="127.0.0.1", port=port, workers=1, log_level="info")
    finally:
        clear_state(os.getpid())
    return 0


def _iniciar_no_fundo(port: int) -> int:
    home().mkdir(parents=True, exist_ok=True)
    with log_file().open("ab") as log:
        child = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "apps.visao_cli", "iniciar", "--porta", str(port)],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + START_WAIT_SECONDS
    while time.monotonic() < deadline:
        if child.poll() is not None:
            print(f"O Visão não subiu. Veja o log: {log_file()}", file=sys.stderr)
            return 1
        status, _ = get_json(port, "/api/health", timeout=1.0)
        if status == 200:
            print(f"Visão em http://127.0.0.1:{port} (processo {child.pid}, log em {log_file()})")
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


def estado() -> int:
    current = running()
    if current is None:
        print("Parado.")
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
    print("\n".join(lines))
    return 0 if status == 200 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="visao", description="O Visão na sua máquina.")
    sub = parser.add_subparsers(dest="comando", required=True)
    start = sub.add_parser("iniciar", help="sobe o Visão em 127.0.0.1, com o worker e o site")
    start.add_argument("--porta", type=int, default=DEFAULT_PORT)
    start.add_argument("--fundo", action="store_true", help="roda em segundo plano, com log")
    sub.add_parser("parar", help="desliga o Visão que está rodando")
    sub.add_parser("estado", help="diz se está rodando, se responde e o último sinal do worker")
    args = parser.parse_args(argv)
    if args.comando == "iniciar":
        return iniciar(args.porta, args.fundo)
    if args.comando == "parar":
        return parar()
    return estado()


if __name__ == "__main__":
    raise SystemExit(main())
