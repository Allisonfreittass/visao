"""ResearchService: runs one search for a knowledge gap and stores what came back, with
provenance (URL, title, excerpt, update date, retrieval time). Results are data, not memory:
nothing found here becomes a memory without going through curation."""

import time

from sqlalchemy.orm import Session

from core.conversation import progress
from infrastructure.database.models import KnowledgeGap, ResearchSession, ResearchSource, User
from integrations.search.base import SearchError, SearchProvider

_WHERE = {
    "tavily": "na web",
    "open-web": "na web",
    "arxiv": "no arXiv",
    "hackernews": "no Hacker News",
}


def _where(name: str) -> str:
    """Where it is searching, in words: "na Wikipédia", "na web"."""
    if name.startswith("wikipedia"):
        return "na Wikipédia"
    return _WHERE.get(name, f"em {name}")


def run_research(
    session: Session,
    *,
    gap: KnowledgeGap,
    owner: User,
    query: str,
    search: SearchProvider,
    max_results: int,
) -> tuple[ResearchSession, list[ResearchSource]]:
    started = time.perf_counter()
    research = ResearchSession(
        gap_id=gap.id, owner_user_id=owner.id, query=query, provider=search.name, status="OK"
    )
    session.add(research)
    session.flush()
    progress.step(f"Pesquisando “{query}”", _where(search.name))
    try:
        results = search.search(query, max_results)
    except SearchError as exc:
        research.status = "ERROR"
        research.error_kind = exc.kind[:50]
        results = []
    research.elapsed_ms = round((time.perf_counter() - started) * 1000)

    seen: set[str] = set()
    sources = []
    for rank, result in enumerate(results, start=1):
        if result.url in seen:
            continue
        seen.add(result.url)
        source = ResearchSource(
            session_id=research.id,
            rank=rank,
            url=result.url,
            title=result.title,
            snippet=result.snippet,
            source=result.source,
            updated_at=result.updated_at,
            retrieved_at=result.retrieved_at,
        )
        session.add(source)
        sources.append(source)
    research.result_count = len(sources)
    if research.status == "OK" and not sources:
        research.status = "EMPTY"
    session.flush()
    return research, sources
