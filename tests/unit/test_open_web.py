import httpx
import pytest

from integrations.search import open_web
from integrations.search.base import SearchError
from integrations.search.open_web import ArxivSearch, HackerNewsSearch

FEED = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/1234.5678</id><title>Um t\xc3\xadtulo</title><summary>Resumo.</summary>
</entry></feed>"""

BOMB = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;">]>
<feed xmlns="http://www.w3.org/2005/Atom"><entry><summary>&lol2;</summary></entry></feed>"""


def _client(body, headers=None) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body, headers=headers))
    )


def test_arxiv_feed_is_parsed():
    (result,) = ArxivSearch(_client(FEED)).search("x")
    assert result.url == "https://arxiv.org/abs/1234.5678" and result.title == "Um título"


def test_arxiv_feed_with_entities_is_refused():
    with pytest.raises(SearchError) as exc:
        ArxivSearch(_client(BOMB)).search("x")
    assert exc.value.kind == "bad_response"


def test_oversized_bodies_are_abandoned_while_streaming(monkeypatch):
    monkeypatch.setattr(open_web, "MAX_RESPONSE_BYTES", 1000)
    chunks_read = []

    def body():
        for _ in range(1000):
            chunks_read.append(1)
            yield b"x" * 100

    with pytest.raises(SearchError) as exc:
        HackerNewsSearch(_client(body())).search("x")
    assert exc.value.kind == "too_large" and len(chunks_read) < 20


def test_declared_oversized_body_is_refused_before_reading(monkeypatch):
    monkeypatch.setattr(open_web, "MAX_RESPONSE_BYTES", 10)
    with pytest.raises(SearchError) as exc:
        HackerNewsSearch(_client(b"{}", {"content-length": "5000"})).search("x")
    assert exc.value.kind == "too_large"
