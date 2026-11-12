"""Reads a public web page for study. The address comes from search results, so it is untrusted:
this runs on the owner's machine and must never become a way to reach it. HTTPS only, public
addresses only (checked again on each redirect, and the connection goes to the very address that
was checked), bounded size, text only.
"""

import html
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from integrations.search.wikipedia import USER_AGENT

MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3
_DROP = re.compile(r"(?is)<(script|style|noscript|svg|nav|header|footer|aside)\b.*?</\1>")
_TAG = re.compile(r"(?s)<[^>]+>")


def _public_address(url: str) -> str | None:
    """The one address this URL will be fetched from, if it and every resolved address are
    public; None otherwise."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    if parts.port not in (None, 443):
        return None
    try:
        infos = socket.getaddrinfo(parts.hostname, 443, proto=socket.IPPROTO_TCP)
        addresses = [ipaddress.ip_address(i[4][0]) for i in infos]
    except (OSError, ValueError):
        return None
    if not addresses or not all(address.is_global for address in addresses):
        return None
    return str(addresses[0])


def is_public_url(url: str) -> bool:
    return _public_address(url) is not None


def _pinned(url: str, address: str) -> str:
    # Connect to the address that was checked, not to whatever a second lookup returns
    # (DNS rebinding); the hostname still goes in Host and SNI, so TLS verifies the real name.
    host = f"[{address}]" if ":" in address else address
    return urlsplit(url)._replace(netloc=host).geturl()


def html_to_text(page: str) -> str:
    body = _DROP.sub(" ", page)
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", body))).strip()


def _fetch(
    url: str, client: httpx.Client, kinds: tuple[str, ...], max_bytes: int = MAX_BYTES
) -> tuple[str, str, str] | None:
    """(body, final URL, content type), or None when it cannot be read safely. Every hop is
    checked again and connected to the very address that was checked."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        address = _public_address(current)
        if address is None:
            return None
        hostname = urlsplit(current).hostname or ""
        try:
            with client.stream(
                "GET",
                _pinned(current, address),
                headers={"Host": hostname},
                extensions={"sni_hostname": hostname},
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    current = urljoin(current, response.headers.get("location", ""))
                    continue
                kind = response.headers.get("content-type", "")
                if response.status_code != 200 or not kind.startswith(kinds):
                    return None
                raw = b""
                for chunk in response.iter_bytes():
                    raw += chunk
                    if len(raw) > max_bytes:
                        break
                return (
                    raw[:max_bytes].decode(response.encoding or "utf-8", "replace"),
                    current,
                    kind,
                )
        except httpx.HTTPError:
            return None
    return None


def read_page(url: str, client: httpx.Client, max_chars: int = 1800) -> str | None:
    """Page text, or None when it cannot be read safely. Never raises for a bad page."""
    got = _fetch(url, client, ("text/html", "text/plain"))
    return (html_to_text(got[0])[:max_chars] or None) if got else None


_META = re.compile(
    r"""(?is)<meta\s+[^>]*?(?:name|property)\s*=\s*["']([^"']+)["'][^>]*?content\s*=\s*["']([^"']*)["']"""
)
_TITLE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_MODULE = re.compile(
    r"""(?is)<script[^>]+type\s*=\s*["']module["'][^>]*src\s*=\s*["']([^"']+)["']"""
)
_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.){12,400})"|`([^`$]{12,400})`')
_CODE_LIKE = re.compile(
    r"[{}<>=;|]|\bfunction\b|\.\w+\(|\.(js|css|png|svg|json)\b|://|\bReact\b|\bnull\b|\bundefined\b"
)
APP_SCRIPT_BYTES = 1_500_000
THIN_PAGE = 300  # characters of visible text below which the page is built by JavaScript


def _meta(page: str) -> dict[str, str]:
    found = {}
    for name, content in _META.findall(page):
        key = name.lower()
        if key in (
            "description",
            "og:title",
            "og:description",
            "og:site_name",
            "twitter:description",
        ):
            found.setdefault(key, html.unescape(content).strip())
    title = _TITLE.search(page)
    if title:
        found.setdefault("title", html.unescape(re.sub(r"\s+", " ", title.group(1))).strip())
    return found


def app_copy(script: str, limit: int = 4000) -> str:
    """The sentences people read in a JavaScript app, taken from string literals in its code:
    several words, mostly letters, nothing that looks like code, paths or errors."""
    seen: list[str] = []
    for double, template in _LITERAL.findall(script):
        text = (double or template).replace("\\n", " ").strip()
        if _CODE_LIKE.search(text) or "Error" in text or "javascript:" in text:
            continue
        if len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", text)) < 3 or text.count(" ") < 2:
            continue
        # Copy people read starts like a sentence; event lists, keys and dev messages do not.
        first = next((ch for ch in text if ch.isalpha()), "")
        if not first.isupper() or re.search(r"\b[a-z]+[A-Z]\w*|_\w", text):
            continue
        if sum(ch.isalpha() or ch in " ,.!?…-–'" for ch in text) / len(text) < 0.85:
            continue
        if text not in seen:
            seen.append(text)
    return "\n".join(seen)[:limit]


def read_page_rich(url: str, client: httpx.Client, max_chars: int = 6000) -> str | None:
    """For a page someone sends: its title and description, the visible text, and, when the page
    is an app built by JavaScript (almost no text in the HTML), the copy found in its main script
    on the same site. None when nothing could be read safely."""
    got = _fetch(url, client, ("text/html", "text/plain"))
    if got is None:
        return None
    page, final, kind = got
    if kind.startswith("text/plain"):
        return page[:max_chars] or None
    meta = _meta(page)
    body = html_to_text(page)
    parts = []
    title = meta.get("og:title") or meta.get("title")
    if title:
        parts.append(f"Título: {title}")
    description = (
        meta.get("description") or meta.get("og:description") or meta.get("twitter:description")
    )
    if description:
        parts.append(f"Descrição: {description}")
    if len(body) >= THIN_PAGE or not _MODULE.search(page):
        if body and body != title:
            parts.append(f"Texto da página:\n{body}")
        return "\n".join(parts)[:max_chars] or None
    script_url = urljoin(final, _MODULE.search(page).group(1))
    copy = ""
    if urlsplit(script_url).hostname == urlsplit(final).hostname:
        script = _fetch(
            script_url, client, ("application/javascript", "text/javascript"), APP_SCRIPT_BYTES
        )
        copy = app_copy(script[0]) if script else ""
    parts.append(
        "A página é um app montado por JavaScript: o HTML quase não tem texto."
        + (
            " Estes são textos do app, tirados do código; podem incluir telas que não aparecem "
            f"logo na entrada:\n{copy}"
            if copy
            else " Não consegui ler os textos do app."
        )
    )
    return "\n".join(parts)[:max_chars]


def default_client(timeout_seconds: float = 10.0) -> httpx.Client:
    return httpx.Client(timeout=timeout_seconds, headers={"User-Agent": USER_AGENT})
