"""Reads a public web page for study. The address comes from search results, so it is untrusted:
this runs on the owner's machine and must never become a way to reach it. HTTPS only, public
addresses only (checked again on each redirect), bounded size, text only.
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


def is_public_url(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return False
    if parts.port not in (None, 443):
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def html_to_text(page: str) -> str:
    body = _DROP.sub(" ", page)
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", body))).strip()


def read_page(url: str, client: httpx.Client, max_chars: int = 1800) -> str | None:
    """Page text, or None when it cannot be read safely. Never raises for a bad page."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        if not is_public_url(current):
            return None
        try:
            with client.stream("GET", current, follow_redirects=False) as response:
                if response.is_redirect:
                    current = urljoin(current, response.headers.get("location", ""))
                    continue
                kind = response.headers.get("content-type", "")
                if response.status_code != 200 or not kind.startswith(("text/html", "text/plain")):
                    return None
                raw = b""
                for chunk in response.iter_bytes():
                    raw += chunk
                    if len(raw) > MAX_BYTES:
                        break
                text = raw[:MAX_BYTES].decode(response.encoding or "utf-8", "replace")
                return html_to_text(text)[:max_chars] or None
        except httpx.HTTPError:
            return None
    return None


def default_client(timeout_seconds: float = 10.0) -> httpx.Client:
    return httpx.Client(timeout=timeout_seconds, headers={"User-Agent": USER_AGENT})
