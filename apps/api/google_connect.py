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
    try:
        return client_from_json(json.loads(path.read_text()))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


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


def client_from_json(data: dict) -> tuple[str, str]:
    """client_id and client_secret of a Google "Desktop app" client, from its downloaded JSON."""
    section = data.get("installed")
    if not isinstance(section, dict):
        raise ValueError(
            "Esse arquivo não é de um cliente 'App para computador' (Desktop app). Crie um assim "
            "no Google Cloud e baixe o JSON de novo."
        )
    client_id, client_secret = section.get("client_id"), section.get("client_secret")
    if not isinstance(client_id, str) or not isinstance(client_secret, str):
        raise ValueError("O arquivo do cliente não tem client_id e client_secret.")
    return client_id.strip(), client_secret.strip()


def pkce() -> tuple[str, str]:
    """A PKCE verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return verifier, challenge.decode()


def auth_url(client_id: str, redirect: str, challenge: str, state: str) -> str:
    return (
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
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
        )
    )


_HINTS = {
    "invalid_client": "a chave secreta não confere com o cliente (ou a chave nova ainda não entrou "
    "em vigor: espere uns minutos)",
    "invalid_grant": "o código do login expirou ou já foi usado: tente de novo",
}


def exchange(
    code: str, client_id: str, client_secret: str, redirect: str, verifier: str
) -> tuple[str | None, str, list[str]]:
    """Trades the sign-in code for a refresh token: (token or None, why not, scopes missing)."""
    try:
        tokens = httpx.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=15,
        )
        answer = tokens.json()
    except (httpx.HTTPError, ValueError):
        return None, "o Google não respondeu à troca do código", []
    refresh = answer.get("refresh_token") if tokens.status_code == 200 else None
    if not refresh:
        reason = (
            answer.get("error_description") or answer.get("error") or f"HTTP {tokens.status_code}"
        )
        hint = _HINTS.get(answer.get("error", ""), "")
        why = f"o Google recusou a troca: {reason}" + (f". Provável: {hint}" if hint else "")
        return None, why, []
    granted = set((answer.get("scope") or "").split())
    return refresh, "", [s.rsplit("/", 1)[-1] for s in SCOPES if s not in granted]


def run(client_file: str | None, server_url: str, *, client_id: str | None = None) -> int:
    if client_id:
        client_secret = getpass.getpass("Chave secreta do cliente (não aparece na tela): ").strip()
        if not client_secret:
            print("Sem a chave secreta não dá para conectar.", file=sys.stderr)
            return 1
    else:
        client_id, client_secret = _client(Path(client_file or "").expanduser())
    server_url = server_url.rstrip("/")
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(16)
    server, port, done, got = _wait_for_code(state)
    redirect = f"http://127.0.0.1:{port}"
    url = auth_url(client_id, redirect, challenge, state)
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
    refresh, why, missing = exchange(got["code"], client_id, client_secret, redirect, verifier)
    if not refresh:
        print(why[0].upper() + why[1:] + ".", file=sys.stderr)
        return 1
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
