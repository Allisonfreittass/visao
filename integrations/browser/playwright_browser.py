"""The browser behind core/browse: Chromium driven by Playwright.

In production the browser runs in its own container with no secrets and no database
(deploy/docker-compose.yml, service `browser`); this process only connects to it. Locally it can
launch Chromium itself. Either way every request the page makes is checked here: HTTPS only,
public addresses only, no pictures, media or fonts (faster, and less to load from strangers).
"""

import ipaddress
import logging
import re
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

from integrations.browser.base import Visit

logger = logging.getLogger(__name__)

TEXT_CHARS = 14_000
LINKS_KEPT = 40
SETTLE_MS = 2500
_BLOCKED_TYPES = {"image", "media", "font"}
# Words a page shows when it wants proof of being human. Seen: stop and say so, never bypass.
_CHALLENGE = re.compile(
    r"captcha|unusual traffic|tráfego incomum|não sou um robô|i'?m not a robot|verify you are "
    r"human|confirme que você é humano|are you a robot|press and hold|access denied",
    re.IGNORECASE,
)


def _public_host(host: str, cache: dict[str, bool]) -> bool:
    if host in cache:
        return cache[host]
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        allowed = bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)
    except (OSError, ValueError):
        allowed = False
    cache[host] = allowed
    return allowed


def allowed_request(url: str, cache: dict[str, bool]) -> bool:
    parts = urlsplit(url)
    if parts.scheme == "data":
        return True
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return False
    if parts.port not in (None, 443):
        return False
    return _public_host(parts.hostname, cache)


class PlaywrightBrowser:
    name = "chromium"

    def __init__(
        self,
        *,
        ws_endpoint: str | None = None,
        executable_path: str | None = None,
        timeout_seconds: float = 20.0,
        locale: str = "pt-BR",
        timezone: str = "America/Sao_Paulo",
    ) -> None:
        self._ws = ws_endpoint or None
        self._executable = executable_path or None
        self._timeout_ms = int(timeout_seconds * 1000)
        self._locale = locale
        self._timezone = timezone

    def visit(self, urls: list[str], on_visit: Callable[[str], None] | None = None) -> list[Visit]:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        if not urls:
            return []
        cache: dict[str, bool] = {}
        try:
            with sync_playwright() as runtime:
                browser = (
                    runtime.chromium.connect(self._ws, timeout=self._timeout_ms)
                    if self._ws
                    else runtime.chromium.launch(headless=True, executable_path=self._executable)
                )
                try:
                    visits = []
                    for url in urls:
                        if on_visit is not None:
                            on_visit(url)
                        visits.append(self._one(browser, url, cache))
                    return visits
                finally:
                    browser.close()
        except PlaywrightError as exc:
            logger.warning(
                "browser unavailable: %s", str(exc)[:120], extra={"event": "browser_down"}
            )
            return [
                Visit(url=u, ok=False, failure="o navegador não está disponível agora")
                for u in urls
            ]

    def _one(self, browser, url: str, cache: dict[str, bool]) -> Visit:
        from playwright.sync_api import Error as PlaywrightError

        if not allowed_request(url, cache):
            return Visit(
                url=url, ok=False, failure="endereço não permitido (só páginas HTTPS públicas)"
            )
        # A fresh context per page: no cookies, storage or logins carried from one site to another.
        context = browser.new_context(
            locale=self._locale,
            timezone_id=self._timezone,
            accept_downloads=False,
            java_script_enabled=True,
            service_workers="block",
            viewport={"width": 1280, "height": 900},
        )
        try:
            context.route("**/*", lambda route: self._filter(route, cache))
            page = context.new_page()
            page.set_default_timeout(self._timeout_ms)
            response = page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=SETTLE_MS * 2)
            except PlaywrightError:
                pass  # busy sites never go idle; what rendered so far is read
            page.wait_for_timeout(SETTLE_MS)
            title = page.title()[:200]
            text = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
            links = page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]')).slice(0, 400)
                    .map(a => [(a.innerText || '').trim().slice(0, 120), a.href])
                    .filter(([t, h]) => t && h.startsWith('https://'))"""
            )
            final = page.url
        except PlaywrightError as exc:
            message = str(exc).splitlines()[0][:120]
            return Visit(url=url, ok=False, failure=f"a página não abriu ({message})")
        finally:
            context.close()
        text = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()
        if response is not None and response.status >= 400:
            return Visit(
                url=url,
                ok=False,
                final_url=final,
                title=title,
                failure=f"o site respondeu {response.status}",
            )
        if _CHALLENGE.search(text[:3000]) and len(text) < 4000:
            return Visit(
                url=url,
                ok=False,
                final_url=final,
                title=title,
                failure="o site pediu para provar que não é robô; não contornei isso",
            )
        if not text:
            return Visit(
                url=url, ok=False, final_url=final, title=title, failure="a página veio vazia"
            )
        unique = tuple(dict.fromkeys((t, h) for t, h in links))[:LINKS_KEPT]
        return Visit(
            url=url, ok=True, final_url=final, title=title, text=text[:TEXT_CHARS], links=unique
        )

    @staticmethod
    def _filter(route, cache: dict[str, bool]) -> None:
        request = route.request
        if request.resource_type in _BLOCKED_TYPES or not allowed_request(request.url, cache):
            route.abort()
            return
        route.continue_()
