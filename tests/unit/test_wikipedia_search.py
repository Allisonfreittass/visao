import httpx
import pytest

from integrations.search.base import SearchError
from integrations.search.wikipedia import API_URL, USER_AGENT, WikipediaSearch


def _provider(handler) -> WikipediaSearch:
    return WikipediaSearch(transport=httpx.MockTransport(handler))


def _handler(calls: list[httpx.Request], pages: dict | None = None, hits: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": hits or []}})
        return httpx.Response(200, json={"query": {"pages": pages or {}}})

    return handler


def test_search_returns_results_in_rank_order_with_provenance() -> None:
    calls: list[httpx.Request] = []
    pages = {
        "2": {
            "pageid": 2,
            "title": "B",
            "fullurl": "https://pt.wikipedia.org/wiki/B",
            "extract": "Texto  B\x07",
            "touched": "2026-10-01T10:00:00Z",
        },
        "1": {
            "pageid": 1,
            "title": "A",
            "fullurl": "https://pt.wikipedia.org/wiki/A",
            "extract": "Texto A",
        },
    }
    provider = _provider(_handler(calls, pages, [{"pageid": 1}, {"pageid": 2}]))

    results = provider.search("algo", 2)

    assert [r.title for r in results] == ["A", "B"]
    assert results[1].snippet == "Texto B"  # control chars and extra spaces removed
    assert results[1].updated_at is not None
    assert all(str(c.url).startswith(API_URL) for c in calls)
    assert calls[0].headers["User-Agent"] == USER_AGENT


def test_results_outside_wikipedia_are_dropped() -> None:
    pages = {"1": {"pageid": 1, "title": "X", "fullurl": "https://evil.example/x"}}
    provider = _provider(_handler([], pages, [{"pageid": 1}]))
    assert provider.search("algo", 1) == []


def test_no_hits_means_empty_not_invented() -> None:
    calls: list[httpx.Request] = []
    assert _provider(_handler(calls)).search("xyzqwe", 3) == []
    assert len(calls) == 1  # no second request when nothing was found


def test_cache_avoids_repeated_requests() -> None:
    calls: list[httpx.Request] = []
    pages = {"1": {"pageid": 1, "title": "A", "fullurl": "https://pt.wikipedia.org/wiki/A"}}
    provider = _provider(_handler(calls, pages, [{"pageid": 1}]))
    provider.search("Algo ", 1)
    provider.search("algo", 1)
    assert len(calls) == 2  # one search + one extract, then served from cache


@pytest.mark.parametrize(
    ("response", "kind"),
    [(httpx.Response(503), "http_503"), (httpx.Response(200, content=b"<html>"), "bad_response")],
)
def test_errors_are_typed(response: httpx.Response, kind: str) -> None:
    with pytest.raises(SearchError) as exc:
        _provider(lambda request: response).search("algo", 1)
    assert exc.value.kind == kind
