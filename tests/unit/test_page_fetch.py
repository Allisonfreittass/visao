import socket

import httpx
import pytest

from integrations.search import fetch
from integrations.search.fetch import read_page

PUBLIC, PRIVATE = "93.184.215.14", "127.0.0.1"


def _resolver(*answers: str):
    calls = []

    def getaddrinfo(host, port, *args, **kwargs):
        address = answers[min(len(calls), len(answers) - 1)]
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    return getaddrinfo, calls


def _client(seen: list[httpx.Request], **response) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            response.get("status", 200),
            headers=response.get("headers", {"content-type": "text/html"}),
            text=response.get("text", "<p>olá mundo</p>"),
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_connection_is_pinned_to_the_checked_address(monkeypatch):
    # A rebinding resolver: public when checked, private on any later lookup.
    getaddrinfo, calls = _resolver(PUBLIC, PRIVATE)
    monkeypatch.setattr(fetch.socket, "getaddrinfo", getaddrinfo)
    seen: list[httpx.Request] = []

    assert read_page("https://example.org/a?b=1", _client(seen)) == "olá mundo"

    assert calls == ["example.org"]
    (request,) = seen
    assert request.url.host == PUBLIC and request.url.path == "/a" and request.url.query == b"b=1"
    assert request.headers["host"] == "example.org"
    assert request.extensions["sni_hostname"] == "example.org"


def test_private_resolution_is_never_requested(monkeypatch):
    getaddrinfo, _ = _resolver(PRIVATE)
    monkeypatch.setattr(fetch.socket, "getaddrinfo", getaddrinfo)
    seen: list[httpx.Request] = []
    assert read_page("https://example.org/", _client(seen)) is None
    assert seen == []


def test_redirect_target_is_checked_and_pinned_again(monkeypatch):
    getaddrinfo, calls = _resolver(PUBLIC, PRIVATE)
    monkeypatch.setattr(fetch.socket, "getaddrinfo", getaddrinfo)
    seen: list[httpx.Request] = []
    client = _client(seen, status=302, headers={"location": "https://internal.example/"})
    assert read_page("https://example.org/", client) is None
    assert calls == ["example.org", "internal.example"] and len(seen) == 1


@pytest.mark.parametrize("address", ["2606:2800:220:1:248:1893:25c8:1946"])
def test_ipv6_addresses_are_bracketed(address):
    assert fetch._pinned("https://example.org/x", address) == f"https://[{address}]/x"
