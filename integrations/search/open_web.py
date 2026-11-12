"""Study sources beyond one encyclopedia, through free public APIs with no key: Wikipedia (pt and
en), arXiv for research, and Hacker News to reach what people are writing now, reading the linked
page. Each source failing alone is not a failure; results are mixed so none crowds out the rest.
"""

import json
from datetime import UTC, datetime
from xml.etree.ElementTree import ParseError  # noqa: S405 (exception type only)

import httpx
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as parse_xml

from integrations.search.base import SearchError, SearchProvider, SearchResult
from integrations.search.fetch import default_client, is_public_url, read_page
from integrations.search.wikipedia import WikipediaSearch

ATOM = "{http://www.w3.org/2005/Atom}"
MAX_RESPONSE_BYTES = 2_000_000


def _get(client: httpx.Client, url: str, params: dict, source: str) -> bytes:
    """The response body, read in chunks and abandoned as soon as it passes the size cap."""
    try:
        with client.stream("GET", url, params=params) as response:
            if response.status_code != 200:
                raise SearchError(f"http_{response.status_code}", f"{source} returned an error")
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                raise SearchError("too_large", f"{source} response too large")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise SearchError("too_large", f"{source} response too large")
            return bytes(body)
    except httpx.HTTPError as exc:
        raise SearchError("network", f"{source}: {type(exc).__name__}") from exc


class ArxivSearch:
    name = "arxiv"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or default_client(15.0)

    def search(self, query: str, max_results: int = 3) -> list[SearchResult]:
        body = _get(
            self._client,
            "https://export.arxiv.org/api/query",
            {"search_query": f"all:{query}", "max_results": str(max_results)},
            "arXiv",
        )
        try:
            root = parse_xml(body)
        except (ParseError, DefusedXmlException) as exc:
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
        body = _get(
            self._client,
            "https://hn.algolia.com/api/v1/search",
            {"query": query, "tags": "story", "hitsPerPage": str(max_results * 2)},
            "Hacker News",
        )
        try:
            hits = json.loads(body).get("hits", [])
        except (ValueError, AttributeError) as exc:
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
