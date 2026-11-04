"""Study sources beyond one encyclopedia, through free public APIs with no key: Wikipedia (pt and
en), arXiv for research, and Hacker News to reach what people are writing now, reading the linked
page. Each source failing alone is not a failure; results are mixed so none crowds out the rest.
"""

import xml.etree.ElementTree as ET  # noqa: S405 (fixed arXiv host, size-bounded response)
from datetime import UTC, datetime

import httpx

from integrations.search.base import SearchError, SearchProvider, SearchResult
from integrations.search.fetch import default_client, is_public_url, read_page
from integrations.search.wikipedia import WikipediaSearch

ATOM = "{http://www.w3.org/2005/Atom}"
MAX_RESPONSE_BYTES = 2_000_000


def _get(client: httpx.Client, url: str, params: dict, source: str) -> httpx.Response:
    try:
        response = client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise SearchError("network", f"{source}: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise SearchError(f"http_{response.status_code}", f"{source} returned an error")
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise SearchError("too_large", f"{source} response too large")
    return response


class ArxivSearch:
    name = "arxiv"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or default_client(15.0)

    def search(self, query: str, max_results: int = 3) -> list[SearchResult]:
        response = _get(
            self._client,
            "https://export.arxiv.org/api/query",
            {"search_query": f"all:{query}", "max_results": str(max_results)},
            "arXiv",
        )
        try:
            root = ET.fromstring(response.text)  # noqa: S314
        except ET.ParseError as exc:
            raise SearchError("bad_response", "invalid arXiv feed") from exc
        now = datetime.now(UTC)
        results = []
        for entry in root.findall(f"{ATOM}entry"):
            url = (entry.findtext(f"{ATOM}id") or "").replace("http://", "https://").strip()
            title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
            summary = " ".join((entry.findtext(f"{ATOM}summary") or "").split())
            if url.startswith("https://arxiv.org/") and summary:
                results.append(SearchResult(url, title[:300], summary[:1800], "arXiv", now))
        return results


class HackerNewsSearch:
    name = "hackernews"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or default_client()

    def search(self, query: str, max_results: int = 3) -> list[SearchResult]:
        response = _get(
            self._client,
            "https://hn.algolia.com/api/v1/search",
            {"query": query, "tags": "story", "hitsPerPage": str(max_results * 2)},
            "Hacker News",
        )
        try:
            hits = response.json().get("hits", [])
        except ValueError as exc:
            raise SearchError("bad_response", "invalid Hacker News JSON") from exc
        now = datetime.now(UTC)
        results = []
        for hit in hits:
            url = hit.get("url") or ""
            if not url or not is_public_url(url):
                continue
            text = read_page(url, self._client)
            if text:
                title = str(hit.get("title", ""))[:300]
                results.append(SearchResult(url, title, text, "Web (via Hacker News)", now))
            if len(results) >= max_results:
                break
        return results


class OpenWebSearch:
    name = "open-web"

    def __init__(self, sources: list[SearchProvider] | None = None) -> None:
        self._sources = sources or [
            WikipediaSearch(),
            WikipediaSearch(language="en"),
            ArxivSearch(),
            HackerNewsSearch(),
        ]

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        per_source, failures = [], []
        for source in self._sources:
            try:
                per_source.append(source.search(query, max_results=2))
            except SearchError as exc:
                failures.append(exc)
        if failures and len(failures) == len(self._sources):
            raise failures[0]
        mixed, seen = [], set()
        for position in range(max(map(len, per_source), default=0)):
            for results in per_source:
                if position < len(results) and results[position].url not in seen:
                    seen.add(results[position].url)
                    mixed.append(results[position])
        return mixed[:max_results]
