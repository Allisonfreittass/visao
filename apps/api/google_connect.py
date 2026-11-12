"""Connects the owner's Google from their computer (docs/GOOGLE.md).

Google only redirects an installed app back to the machine that asked, so the sign-in happens
here: a one-shot server on 127.0.0.1 receives the code, it is exchanged (with PKCE) for a refresh
token, and that goes straight to the Visão server over HTTPS, signed in as the owner. Nothing is
printed or written to disk; the server keeps it encrypted.
"""

import base64
import getpass
import hashlib
import http.server
import json
import secrets
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from integrations.google.client import AUTH_URL, SCOPES, TOKEN_URL

PAGE = (
    "<!doctype html><meta charset=utf-8><title>Visão</title>"
    "<body style='font:16px system-ui;background:#090E10;color:#E6E9E6;padding:40px'>"
    "<p>{text}</p><p>Pode fechar esta aba e voltar ao terminal.</p></body>"
)


def _client(path: Path) -> tuple[str, str]:
    data = json.loads(path.read_text())
    section = data.get("installed") or data.get("web") or {}
    if "installed" not in data:
        raise SystemExit(
            "Esse arquivo não é de um cliente 'App para computador' (Desktop app). Crie um assim "
            "no Google Cloud e baixe o JSON de novo."
        )
    return section["client_id"], section["client_secret"]


def _wait_for_code(state: str) -> tuple[http.server.HTTPServer, int, threading.Event, dict]:
    got: dict = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            query = parse_qs(urlsplit(self.path).query)
            ok = query.get("state", [""])[0] == state and "code" in query
            if ok:
                got["code"] = query["code"][0]
            else:
                got["error"] = query.get("error", ["resposta inesperada"])[0]
            body = PAGE.format(text="Pronto, voltei ao Visão." if ok else "Não deu certo.")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())
            done.set()

        def log_message(self, *args):  # quiet
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1], done, got


def run(client_file: str, server_url: str) -> int:
    client_id, client_secret = _client(Path(client_file).expanduser())
    server_url = server_url.rstrip("/")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    state = secrets.token_urlsafe(16)
    server, port, done, got = _wait_for_code(state)
    redirect = f"http://127.0.0.1:{port}"
    url = (
        AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": " ".join(SCOPES),
                "access_type": "offline",
                "prompt": "consent",
                "code_challenge": challenge.decode(),
                "code_challenge_method": "S256",
                "state": state,
            }
        )
    )
    print("Abrindo o login do Google no navegador. Se não abrir, cole este endereço:\n")
    print(url + "\n")
    webbrowser.open(url)
    if not done.wait(timeout=300):
        print("Passaram 5 minutos sem resposta. Rode de novo.", file=sys.stderr)
        return 1
    server.shutdown()
    if "code" not in got:
        print(f"O Google não autorizou: {got.get('error')}.", file=sys.stderr)
        return 1
    tokens = httpx.post(
        TOKEN_URL,
        data={
            "code": got["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
        timeout=15,
    )
    refresh = tokens.json().get("refresh_token") if tokens.status_code == 200 else None
    if not refresh:
        print("O Google não devolveu a autorização de longo prazo. Rode de novo.", file=sys.stderr)
        return 1
    granted = set((tokens.json().get("scope") or "").split())
    missing = [s.rsplit("/", 1)[-1] for s in SCOPES if s not in granted]
    if missing:
        print(f"Aviso: você não marcou {', '.join(missing)}; essa parte não vai funcionar.")

    print("Agora entre no Visão para guardar a conexão lá.")
    email = input("Email do Visão: ").strip()
    password = getpass.getpass("Senha do Visão: ")
    login = httpx.post(
        f"{server_url}/api/auth/login", data={"username": email, "password": password}, timeout=15
    )
    if login.status_code != 200:
        print("Email ou senha do Visão não conferem.", file=sys.stderr)
        return 1
    token = login.json()["access_token"]
    saved = httpx.post(
        f"{server_url}/api/google/connect",
        headers={"Authorization": f"Bearer {token}"},
        json={"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh},
        timeout=30,
    )
    if saved.status_code != 200:
        print(f"O Visão não aceitou: {saved.text[:300]}", file=sys.stderr)
        return 1
    print(f"Conectado: {saved.json().get('email')}. Gerencie em Ajustes › Google.")
    return 0
